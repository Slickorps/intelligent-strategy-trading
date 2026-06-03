"""Unit tests for ML factor engine.

Tests MLFactor, WalkForwardOptimizer, MLFactorRegistry, and their
interactions. Uses mock data to avoid sklearn dependency issues if
not installed.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from ist.risk.ml_factors import (
    MLFactor,
    MLFactorConfig,
    MLFactorRegistry,
    PredictionResult,
    TrainingResult,
    WalkForwardOptimizer,
    WalkForwardSplit,
    registry,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_features() -> pd.DataFrame:
    """Create sample feature DataFrame for testing."""
    np.random.seed(42)
    return pd.DataFrame({
        "rsi": np.random.uniform(0, 100, 200),
        "momentum": np.random.randn(200),
        "volatility": np.random.uniform(0.1, 2.0, 200),
        "volume": np.random.randint(1000, 10000, 200),
    })


@pytest.fixture
def sample_target() -> pd.Series:
    """Create sample binary target for classification."""
    np.random.seed(42)
    return pd.Series(np.random.randint(0, 2, 200))


@pytest.fixture
def sample_regression_target() -> pd.Series:
    """Create sample continuous target for regression."""
    np.random.seed(42)
    return pd.Series(np.random.randn(200))


@pytest.fixture
def ml_factor() -> MLFactor:
    """Create a basic MLFactor instance."""
    return MLFactor(
        name="test_factor",
        model_type="RandomForestClassifier",
        model_params={"n_estimators": 10, "max_depth": 3},
        feature_columns=["rsi", "momentum", "volatility"],
    )


@pytest.fixture
def trained_factor(ml_factor, sample_features, sample_target) -> MLFactor:
    """Create a pre-trained MLFactor instance."""
    return ml_factor.fit(sample_features, sample_target)


@pytest.fixture
def clean_registry():
    """Provide a fresh registry for each test."""
    reg = MLFactorRegistry()
    yield reg


# ---------------------------------------------------------------------------
# MLFactorConfig
# ---------------------------------------------------------------------------

class TestMLFactorConfig:
    def test_default_config(self):
        """Config should set sensible defaults."""
        cfg = MLFactorConfig(name="test")
        assert cfg.name == "test"
        assert cfg.model_type == "RandomForestClassifier"
        assert cfg.model_params == {}
        assert cfg.feature_columns == []
        assert cfg.target_column == "target"
        assert cfg.test_size == 0.2

    def test_custom_config(self):
        """Config should accept custom values."""
        cfg = MLFactorConfig(
            name="custom",
            model_type="GradientBoostingClassifier",
            model_params={"n_estimators": 200},
            feature_columns=["a", "b"],
            target_column="y",
            test_size=0.3,
        )
        assert cfg.name == "custom"
        assert cfg.model_type == "GradientBoostingClassifier"
        assert cfg.model_params == {"n_estimators": 200}


# ---------------------------------------------------------------------------
# TrainingResult / PredictionResult
# ---------------------------------------------------------------------------

class TestResults:
    def test_training_result_to_dict(self):
        """TrainingResult.to_dict() should return correct keys."""
        tr = TrainingResult(
            model_id="test_abc123",
            model_type="RandomForestClassifier",
            feature_columns=["rsi"],
            train_score=0.95,
            test_score=0.82,
            feature_importances={"rsi": 1.0},
            training_date="2025-01-01T00:00:00",
            num_samples=100,
            version="1.0.0",
            path="/tmp/model.joblib",
        )
        d = tr.to_dict()
        assert d["model_id"] == "test_abc123"
        assert d["train_score"] == 0.95
        assert d["test_score"] == 0.82
        assert d["feature_importances"] == {"rsi": 1.0}

    def test_prediction_result_to_dict(self):
        """PredictionResult.to_dict() should return correct keys."""
        pr = PredictionResult(
            model_id="test_abc123",
            predictions=[1, 0, 1],
            confidence=0.9,
            feature_values={"rsi": 45.0},
        )
        d = pr.to_dict()
        assert d["model_id"] == "test_abc123"
        assert d["predictions"] == [1, 0, 1]
        assert d["confidence"] == 0.9
        assert "probabilities" not in d

    def test_prediction_result_with_proba(self):
        """PredictionResult with probabilities should include them."""
        pr = PredictionResult(
            model_id="test_abc123",
            predictions=[1, 0],
            probabilities=[[0.2, 0.8], [0.7, 0.3]],
            confidence=0.85,
            feature_values={},
        )
        d = pr.to_dict()
        assert d["probabilities"] == [[0.2, 0.8], [0.7, 0.3]]


# ---------------------------------------------------------------------------
# MLFactor — Lifecycle
# ---------------------------------------------------------------------------

class TestMLFactorLifecycle:
    def test_initial_state(self, ml_factor):
        """MLFactor should start unfitted with no pipeline."""
        assert ml_factor.is_fitted is False
        assert ml_factor.pipeline is None
        assert ml_factor.training_result is None
        assert ml_factor.feature_importances == {}
        assert ml_factor.name == "test_factor"

    def test_fit_updates_state(self, trained_factor):
        """After fit, factor should be fitted with results."""
        assert trained_factor.is_fitted is True
        assert trained_factor.pipeline is not None
        assert trained_factor.training_result is not None
        assert trained_factor.training_result.model_id.startswith("test_factor_")
        assert trained_factor.training_result.num_samples == 200

    def test_predict_after_fit(self, trained_factor, sample_features):
        """Trained factor should produce predictions."""
        preds = trained_factor.predict(sample_features)
        assert len(preds) == 200
        assert all(isinstance(p, (int, np.integer)) for p in preds)

    def test_predict_before_fit_raises(self, ml_factor, sample_features):
        """Predicting on unfitted model should raise RuntimeError."""
        with pytest.raises(RuntimeError, match="Model must be trained"):
            ml_factor.predict(sample_features)

    def test_predict_proba_after_fit(self, trained_factor, sample_features):
        """Trained classifier should support predict_proba."""
        proba = trained_factor.predict_proba(sample_features)
        assert proba.shape == (200, 2)
        # Probabilities should sum to 1
        assert np.allclose(proba.sum(axis=1), 1.0)

    def test_predict_proba_before_fit_raises(self, ml_factor, sample_features):
        """predict_proba on unfitted model should raise."""
        with pytest.raises(RuntimeError, match="Model must be trained"):
            ml_factor.predict_proba(sample_features)

    def test_save_load_roundtrip(self, trained_factor):
        """Save and load should preserve model behavior."""
        with tempfile.TemporaryDirectory() as tmp:
            save_path = trained_factor.save(tmp)
            loaded = MLFactor.load(save_path)

        assert loaded.is_fitted is True
        assert loaded.name == trained_factor.name
        assert loaded.model_type == trained_factor.model_type
        assert loaded.feature_columns == trained_factor.feature_columns

    def test_save_untrained_raises(self, ml_factor):
        """Saving untrained model should raise RuntimeError."""
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(RuntimeError, match="Cannot save untrained"):
                ml_factor.save(tmp)

    def test_load_nonexistent_raises(self):
        """Loading non-existent file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            MLFactor.load("/nonexistent/path/model.joblib")

    def test_feature_importances_populated(self, trained_factor):
        """After fit, feature importances should be non-empty."""
        fi = trained_factor.feature_importances
        assert len(fi) > 0
        assert all(col in fi for col in ["rsi", "momentum", "volatility"])


# ---------------------------------------------------------------------------
# MLFactor — Custom Feature Transforms
# ---------------------------------------------------------------------------

class TestFeatureTransforms:
    def test_add_feature(self, ml_factor):
        """add_feature should register a transform and add to feature_columns."""
        ml_factor.add_feature("custom_feat", lambda df: df["rsi"] * 2)
        assert "custom_feat" in ml_factor.feature_columns

    def test_custom_feature_used_in_fit(self, ml_factor, sample_features, sample_target):
        """Custom transforms should be applied during fit."""
        ml_factor.add_feature("rsi_squared", lambda df: df["rsi"] ** 2)
        # Add feature to columns that exists in data
        ml_factor.feature_columns = ["rsi", "momentum", "volatility", "rsi_squared"]
        ml_factor.fit(sample_features, sample_target)
        assert ml_factor.is_fitted is True
        assert "rsi_squared" in ml_factor.feature_importances


# ---------------------------------------------------------------------------
# MLFactor — Different Model Types
# ---------------------------------------------------------------------------

class TestModelTypes:
    @pytest.mark.parametrize("model_type,is_classifier", [
        ("RandomForestClassifier", True),
        ("RandomForestRegressor", False),
        ("LogisticRegression", True),
    ])
    def test_various_models(
        self, model_type, is_classifier, sample_features, sample_target
    ):
        """Different model types should train successfully."""
        # Use regression target for regressor
        target = (
            sample_target
            if is_classifier
            else pd.Series(np.random.randn(200))
        )
        factor = MLFactor(
            name=model_type,
            model_type=model_type,
            model_params={"n_estimators": 5, "max_depth": 2}
            if "Forest" in model_type or "Gradient" in model_type
            else {"max_iter": 100},
            feature_columns=["rsi", "momentum", "volatility"],
        )
        factor.fit(sample_features, target)
        assert factor.is_fitted is True
        preds = factor.predict(sample_features)
        assert len(preds) == 200
        assert factor.training_result is not None

    def test_unknown_model_type_raises(self):
        """Unknown model type should raise ValueError."""
        factor = MLFactor(name="bad", model_type="NonExistentModel")
        with pytest.raises(ValueError, match="Unknown model type"):
            factor._load_model_class()

    def test_auto_feature_detection(self, sample_features, sample_target):
        """With no feature_columns specified, should use all numeric columns."""
        factor = MLFactor(
            name="auto_feat",
            model_type="RandomForestClassifier",
            model_params={"n_estimators": 5, "max_depth": 3},
        )
        factor.fit(sample_features, sample_target)
        assert len(factor.feature_columns) == 4  # all numeric columns
        assert "rsi" in factor.feature_columns
        assert "volume" in factor.feature_columns


# ---------------------------------------------------------------------------
# WalkForwardSplit
# ---------------------------------------------------------------------------

class TestWalkForwardSplit:
    def test_split_generates_folds(self):
        """WalkForwardSplit should yield (train_idx, test_idx) pairs."""
        n = 500
        split = WalkForwardSplit(train_size=252, test_size=63, step=21)
        X_dummy = pd.DataFrame(np.random.randn(n, 3))

        folds = list(split.split(X_dummy))
        assert len(folds) > 0
        for train_idx, test_idx in folds:
            assert len(train_idx) == 252
            assert len(test_idx) == 63
            assert max(test_idx) > max(train_idx)  # test is after train

    def test_get_n_splits(self):
        """get_n_splits should return correct count."""
        split = WalkForwardSplit(train_size=252, test_size=63, step=21)
        # With 500 samples: floor((500 - 252 - 63) / 21) + 1 = 8 + 1 = 9?
        # (500-315)=185 // 21 = 8, +1 = 9
        assert split.get_n_splits(X=np.zeros((500, 3))) == 9

    def test_zero_splits_for_small_data(self):
        """For data smaller than train+test, should return 1 split (start=0 only)."""
        split = WalkForwardSplit(train_size=252, test_size=63, step=21)
        assert split.get_n_splits(X=np.zeros((100, 3))) == 1

    def test_split_no_overlap(self):
        """Train and test indices should not overlap."""
        split = WalkForwardSplit(train_size=100, test_size=30, step=50)
        X_dummy = pd.DataFrame(np.random.randn(300, 3))
        for train_idx, test_idx in split.split(X_dummy):
            assert len(set(train_idx) & set(test_idx)) == 0


# ---------------------------------------------------------------------------
# WalkForwardOptimizer
# ---------------------------------------------------------------------------

class TestWalkForwardOptimizer:
    def test_evaluate_returns_results(self, sample_features, sample_target):
        """WalkForwardOptimizer.evaluate should return TrainingResult list."""
        data = sample_features.copy()
        data["target"] = sample_target

        factor = MLFactor(
            name="wf_test",
            model_type="RandomForestClassifier",
            model_params={"n_estimators": 5, "max_depth": 3},
            feature_columns=["rsi", "momentum", "volatility"],
        )
        split = WalkForwardSplit(train_size=100, test_size=30, step=30)
        optimizer = WalkForwardOptimizer(factor, split=split)
        results = optimizer.evaluate(data, target_column="target")

        assert len(results) > 0
        for r in results:
            assert r.model_id.startswith("wf_test_fold")
            assert isinstance(r.test_score, float)

    def test_get_summary(self, sample_features, sample_target):
        """get_summary should return dict with statistics."""
        data = sample_features.copy()
        data["target"] = sample_target

        factor = MLFactor(
            name="wf_summary",
            model_type="RandomForestClassifier",
            model_params={"n_estimators": 5, "max_depth": 3},
            feature_columns=["rsi", "momentum"],
        )
        split = WalkForwardSplit(train_size=100, test_size=30, step=30)
        optimizer = WalkForwardOptimizer(factor, split=split)
        optimizer.evaluate(data, target_column="target")

        summary = optimizer.get_summary()
        assert "num_folds" in summary
        assert "mean_test_score" in summary
        assert "std_test_score" in summary
        assert "min_test_score" in summary
        assert "max_test_score" in summary
        assert summary["factor_name"] == "wf_summary"
        assert summary["num_folds"] > 0

    def test_empty_summary_before_evaluate(self):
        """Before evaluate, get_summary should return no_results status."""
        factor = MLFactor(name="empty", model_type="RandomForestClassifier")
        split = WalkForwardSplit(train_size=100, test_size=30, step=30)
        optimizer = WalkForwardOptimizer(factor, split=split)
        assert optimizer.get_summary() == {"status": "no_results"}


# ---------------------------------------------------------------------------
# MLFactorRegistry
# ---------------------------------------------------------------------------

class TestMLFactorRegistry:
    def test_register_model(self, trained_factor, clean_registry):
        """Register should assign a model_id and store the model."""
        model_id = clean_registry.register(trained_factor)
        assert model_id is not None
        assert model_id.startswith("test_factor_")
        assert clean_registry.get(model_id) is trained_factor

    def test_get_result(self, trained_factor, clean_registry):
        """get_result should return the stored TrainingResult."""
        model_id = clean_registry.register(trained_factor)
        result = clean_registry.get_result(model_id)
        assert result is not None
        assert result.model_id == model_id

    def test_list_models(self, trained_factor, clean_registry):
        """list_models should return list of result dicts."""
        clean_registry.register(trained_factor)
        models = clean_registry.list_models()
        assert len(models) == 1
        assert models[0]["model_type"] == "RandomForestClassifier"

    def test_register_untrained_raises(self, ml_factor, clean_registry):
        """Registering unfitted model should raise ValueError."""
        with pytest.raises(ValueError, match="unfitted"):
            clean_registry.register(ml_factor)

    def test_remove_model(self, trained_factor, clean_registry):
        """remove should delete the model and return True."""
        model_id = clean_registry.register(trained_factor)
        assert clean_registry.remove(model_id) is True
        assert clean_registry.get(model_id) is None

    def test_remove_nonexistent_returns_false(self, clean_registry):
        """Removing non-existent model should return False."""
        assert clean_registry.remove("nonexistent") is False

    def test_clear_registry(self, trained_factor, clean_registry):
        """clear should remove all models."""
        clean_registry.register(trained_factor)
        assert len(clean_registry.list_models()) == 1
        clean_registry.clear()
        assert len(clean_registry.list_models()) == 0

    def test_save_dir_persistence(self, trained_factor):
        """With save dir set, register should persist to disk."""
        with tempfile.TemporaryDirectory() as tmp:
            reg = MLFactorRegistry()
            reg.set_save_dir(tmp)
            model_id = reg.register(trained_factor)

            # Should have created .joblib and .json files
            files = list(Path(tmp).iterdir())
            assert len(files) >= 2  # .joblib + .json
            assert any(f.suffix == ".joblib" for f in files)
            assert any(f.suffix == ".json" for f in files)

    def test_global_registry_singleton(self):
        """The module-level 'registry' should be an MLFactorRegistry instance."""
        from ist.risk.ml_factors import registry as global_reg
        assert isinstance(global_reg, MLFactorRegistry)


# ---------------------------------------------------------------------------
# Error handling paths
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_fit_missing_feature_columns_raises(self, ml_factor):
        """If none of the specified feature columns exist, fit should raise."""
        bad_data = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        with pytest.raises(ValueError, match="None of the specified feature columns"):
            ml_factor.fit(bad_data, pd.Series([0, 1, 0]))

    def test_predict_proba_unsupported_model_raises(self):
        """Models without predict_proba should raise AttributeError."""
        factor = MLFactor(
            name="svr_test",
            model_type="SVR",
            model_params={"max_iter": 100},
            feature_columns=["rsi", "momentum"],
        )
        X = pd.DataFrame({"rsi": np.random.randn(50), "momentum": np.random.randn(50)})
        y = pd.Series(np.random.randn(50))
        factor.fit(X, y)

        X_pred = pd.DataFrame({"rsi": np.random.randn(10), "momentum": np.random.randn(10)})
        with pytest.raises(AttributeError, match="does not support predict_proba"):
            factor.predict_proba(X_pred)

    def test_predict_with_missing_columns(self, trained_factor):
        """Predict should raise ValueError when required columns are missing,
        as sklearn's StandardScaler enforces feature name consistency."""
        X = pd.DataFrame({"rsi": np.random.randn(10)})  # only 1 of 3 columns
        with pytest.raises(ValueError, match="missing"):
            trained_factor.predict(X)

    def test_fit_with_non_numeric_target_string(self, sample_features):
        """Fit should handle non-numeric edge cases (string target)."""
        factor = MLFactor(
            name="str_target",
            model_type="RandomForestClassifier",
            model_params={"n_estimators": 5, "max_depth": 2},
            feature_columns=["rsi", "momentum", "volatility"],
        )
        target = pd.Series(["A", "B"] * 100)
        factor.fit(sample_features, target)
        assert factor.is_fitted is True


# ---------------------------------------------------------------------------
# Edge cases — small data, single feature
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_single_feature(self):
        """MLFactor should work with a single feature."""
        X = pd.DataFrame({"x": np.random.randn(50)})
        y = pd.Series(np.random.randint(0, 2, 50))
        factor = MLFactor(
            name="single_feat",
            model_type="LogisticRegression",
            model_params={"max_iter": 200},
            feature_columns=["x"],
        )
        factor.fit(X, y)
        assert factor.is_fitted is True
        preds = factor.predict(X)
        assert len(preds) == 50

    def test_minimal_data(self):
        """MLFactor should handle minimal data (just enough for train/test split)."""
        X = pd.DataFrame({"a": np.random.randn(20), "b": np.random.randn(20)})
        y = pd.Series(np.random.randint(0, 2, 20))
        factor = MLFactor(
            name="minimal",
            model_type="RandomForestClassifier",
            model_params={"n_estimators": 5, "max_depth": 2},
            feature_columns=["a", "b"],
        )
        factor.fit(X, y)
        assert factor.is_fitted is True

    def test_model_id_uniqueness(self, sample_features, sample_target):
        """Each fit should generate a unique model_id."""
        factor = MLFactor(
            name="unique",
            model_type="RandomForestClassifier",
            model_params={"n_estimators": 5, "max_depth": 2},
            feature_columns=["rsi", "momentum"],
        )
        factor.fit(sample_features, sample_target)
        id1 = factor.training_result.model_id

        factor2 = MLFactor(
            name="unique",
            model_type="RandomForestClassifier",
            model_params={"n_estimators": 5, "max_depth": 2},
            feature_columns=["rsi", "momentum"],
        )
        factor2.fit(sample_features, sample_target)
        id2 = factor2.training_result.model_id

        assert id1 != id2
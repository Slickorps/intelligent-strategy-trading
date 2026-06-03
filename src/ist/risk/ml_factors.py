"""Machine Learning factor engine with sklearn integration.

Provides MLFactor class for sklearn Pipeline encapsulation,
walk-forward optimization framework, and model persistence.
"""

import hashlib
import json
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Optional, Union

import numpy as np
import pandas as pd
from joblib import dump, load

from ist.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class MLFactorConfig:
    """Configuration for an ML factor."""

    name: str
    model_type: str = "RandomForestClassifier"
    model_params: dict[str, Any] = field(default_factory=dict)
    feature_columns: list[str] = field(default_factory=list)
    target_column: str = "target"
    test_size: float = 0.2
    random_state: int = 42
    version: str = "1.0.0"


@dataclass
class TrainingResult:
    """Result of a model training run."""

    model_id: str
    model_type: str
    feature_columns: list[str]
    train_score: float
    test_score: float
    feature_importances: dict[str, float]
    training_date: str
    num_samples: int
    version: str
    path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_type": self.model_type,
            "feature_columns": self.feature_columns,
            "train_score": self.train_score,
            "test_score": self.test_score,
            "feature_importances": self.feature_importances,
            "training_date": self.training_date,
            "num_samples": self.num_samples,
            "version": self.version,
            "path": self.path,
        }


@dataclass
class PredictionResult:
    """Result of a model prediction."""

    model_id: str
    predictions: list[Union[int, float]]
    probabilities: Optional[list[list[float]]] = None
    confidence: float = 0.0
    feature_values: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "model_id": self.model_id,
            "predictions": self.predictions,
            "confidence": self.confidence,
            "feature_values": self.feature_values,
        }
        if self.probabilities is not None:
            result["probabilities"] = self.probabilities
        return result


# ---------------------------------------------------------------------------
# MLFactor — sklearn Pipeline wrapper
# ---------------------------------------------------------------------------

class MLFactor:
    """Machine Learning factor that wraps a sklearn Pipeline.

    Provides a unified interface for:
    - Feature engineering with optional transforms
    - Pipeline fitting and prediction
    - Model persistence via joblib
    - Feature importance extraction

    Examples:
        >>> from sklearn.ensemble import RandomForestClassifier
        >>> factor = MLFactor(
        ...     name="rsi_momentum_ml",
        ...     model_type="RandomForestClassifier",
        ...     model_params={"n_estimators": 100, "max_depth": 5},
        ...     feature_columns=["rsi", "momentum", "volatility"],
        ... )
        >>> factor.fit(X_train, y_train)
        >>> preds = factor.predict(X_test)
    """

    MODELS = {
        "RandomForestClassifier": "sklearn.ensemble.RandomForestClassifier",
        "RandomForestRegressor": "sklearn.ensemble.RandomForestRegressor",
        "GradientBoostingClassifier": "sklearn.ensemble.GradientBoostingClassifier",
        "GradientBoostingRegressor": "sklearn.ensemble.GradientBoostingRegressor",
        "LogisticRegression": "sklearn.linear_model.LogisticRegression",
        "SVC": "sklearn.svm.SVC",
        "SVR": "sklearn.svm.SVR",
        "XGBClassifier": "xgboost.XGBClassifier",
        "XGBRegressor": "xgboost.XGBRegressor",
    }

    def __init__(
        self,
        name: str,
        model_type: str = "RandomForestClassifier",
        model_params: Optional[dict[str, Any]] = None,
        feature_columns: Optional[list[str]] = None,
        target_column: str = "target",
        random_state: int = 42,
    ) -> None:
        self.name = name
        self.model_type = model_type
        self.model_params = model_params or {}
        self.feature_columns = feature_columns or []
        self.target_column = target_column
        self.random_state = random_state

        self._pipeline: Optional[Any] = None
        self._feature_transforms: dict[str, Callable] = {}
        self._is_fitted: bool = False
        self._training_result: Optional[TrainingResult] = None
        self._feature_importances: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Feature engineering
    # ------------------------------------------------------------------

    def add_feature(self, column: str, transform: Callable) -> None:
        """Register a custom feature transform.

        Args:
            column: Name of the generated feature column.
            transform: Callable that takes a DataFrame and returns a Series.
        """
        self._feature_transforms[column] = transform
        if column not in self.feature_columns:
            self.feature_columns.append(column)
        logger.debug("Registered feature transform", column=column)

    def _apply_transforms(self, data: pd.DataFrame) -> pd.DataFrame:
        """Apply all registered feature transforms."""
        df = data.copy()
        for col, fn in self._feature_transforms.items():
            try:
                df[col] = fn(data)
            except Exception as exc:
                logger.warning(
                    "Feature transform failed",
                    column=col,
                    error=str(exc),
                )
        return df

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _load_model_class(self) -> Any:
        """Import and return the model class based on model_type."""
        import_path = self.MODELS.get(self.model_type)
        if import_path is None:
            raise ValueError(
                f"Unknown model type '{self.model_type}'. "
                f"Available: {list(self.MODELS.keys())}"
            )

        module_name, class_name = import_path.rsplit(".", 1)
        try:
            module = __import__(module_name, fromlist=[class_name])
            return getattr(module, class_name)
        except ImportError:
            # Fallback: try sklearn directly
            if "XGB" in self.model_type:
                raise ImportError(
                    "xgboost is not installed. "
                    "Install with: pip install xgboost"
                )
            from sklearn.ensemble import (
                RandomForestClassifier,
                RandomForestRegressor,
                GradientBoostingClassifier,
                GradientBoostingRegressor,
            )
            from sklearn.linear_model import LogisticRegression
            from sklearn.svm import SVC, SVR

            FALLBACK = {
                "RandomForestClassifier": RandomForestClassifier,
                "RandomForestRegressor": RandomForestRegressor,
                "GradientBoostingClassifier": GradientBoostingClassifier,
                "GradientBoostingRegressor": GradientBoostingRegressor,
                "LogisticRegression": LogisticRegression,
                "SVC": SVC,
                "SVR": SVR,
            }
            cls = FALLBACK.get(self.model_type)
            if cls is None:
                raise
            return cls

    def _build_pipeline(self) -> Any:
        """Build a sklearn Pipeline with StandardScaler + estimator."""
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        model_class = self._load_model_class()
        params = dict(self.model_params)

        # Only pass random_state to models that accept it
        import inspect
        if "random_state" in inspect.signature(model_class.__init__).parameters:
            params.setdefault("random_state", self.random_state)

        estimator = model_class(**params)
        return Pipeline(
            [
                ("scaler", StandardScaler()),
                ("estimator", estimator),
            ]
        )

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def fit(
        self,
        X: pd.DataFrame,
        y: Union[pd.Series, np.ndarray],
    ) -> "MLFactor":
        """Fit the ML model on training data.

        Args:
            X: Feature DataFrame.
            y: Target Series or array.

        Returns:
            Self for chaining.
        """
        from sklearn.model_selection import train_test_split

        # Apply feature transforms
        X = self._apply_transforms(X)

        # Select feature columns
        if self.feature_columns:
            available = [c for c in self.feature_columns if c in X.columns]
            if not available:
                raise ValueError(
                    f"None of the specified feature columns {self.feature_columns} "
                    f"found in input data. Available columns: {list(X.columns)}"
                )
            X = X[available]
        else:
            # Use all numeric columns
            available = list(X.select_dtypes(include=[np.number]).columns)
            X = X[available]
            self.feature_columns = available

        # Split into train/test
        X_train, X_test, y_train, y_test = train_test_split(
            X, y,
            test_size=0.2,
            random_state=self.random_state,
            shuffle=False,
        )

        # Build and train pipeline
        self._pipeline = self._build_pipeline()
        self._pipeline.fit(X_train, y_train)

        # Evaluate
        if hasattr(self._pipeline.named_steps["estimator"], "predict"):
            if hasattr(self._pipeline.named_steps["estimator"], "predict_proba"):
                train_score = self._pipeline.score(X_train, y_train)
                test_score = self._pipeline.score(X_test, y_test)
            else:
                train_score = self._pipeline.score(X_train, y_train)
                test_score = self._pipeline.score(X_test, y_test)
        else:
            train_score = 0.0
            test_score = 0.0

        # Extract feature importances
        self._extract_feature_importances()

        # Store result metadata
        model_id = self._generate_model_id()
        self._training_result = TrainingResult(
            model_id=model_id,
            model_type=self.model_type,
            feature_columns=self.feature_columns,
            train_score=train_score,
            test_score=test_score,
            feature_importances=self._feature_importances,
            training_date=datetime.utcnow().isoformat(),
            num_samples=len(X),
            version="1.0.0",
            path="",
        )
        self._is_fitted = True

        logger.info(
            "ML model trained",
            name=self.name,
            model_type=self.model_type,
            train_score=round(train_score, 4),
            test_score=round(test_score, 4),
            num_features=len(self.feature_columns),
            num_samples=len(X),
        )

        return self

    def _extract_feature_importances(self) -> None:
        """Extract feature importances or coefficients from trained model."""
        if self._pipeline is None:
            return

        estimator = self._pipeline.named_steps["estimator"]

        if hasattr(estimator, "feature_importances_"):
            importances = estimator.feature_importances_
        elif hasattr(estimator, "coef_"):
            importances = np.abs(estimator.coef_[0]) if estimator.coef_.ndim > 1 else np.abs(estimator.coef_)
        else:
            importances = np.ones(len(self.feature_columns)) / len(self.feature_columns)

        self._feature_importances = dict(
            zip(self.feature_columns, importances.tolist())
        )

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Make predictions using the trained model.

        Args:
            X: Feature DataFrame.

        Returns:
            Array of predictions.
        """
        if not self._is_fitted or self._pipeline is None:
            raise RuntimeError("Model must be trained before prediction. Call fit() first.")

        X = self._apply_transforms(X)
        if self.feature_columns:
            available = [c for c in self.feature_columns if c in X.columns]
            X = X[available]

        return self._pipeline.predict(X)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Predict class probabilities.

        Args:
            X: Feature DataFrame.

        Returns:
            Array of probability estimates.
        """
        if not self._is_fitted or self._pipeline is None:
            raise RuntimeError("Model must be trained before prediction. Call fit() first.")

        estimator = self._pipeline.named_steps["estimator"]
        if not hasattr(estimator, "predict_proba"):
            raise AttributeError(
                f"Model type '{self.model_type}' does not support predict_proba"
            )

        X = self._apply_transforms(X)
        if self.feature_columns:
            available = [c for c in self.feature_columns if c in X.columns]
            X = X[available]

        return self._pipeline.predict_proba(X)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: Union[str, Path]) -> str:
        """Save the trained model to disk using joblib.

        Args:
            path: Directory path to save the model.

        Returns:
            Full path to the saved model file.
        """
        if not self._is_fitted or self._pipeline is None:
            raise RuntimeError("Cannot save untrained model.")

        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        model_id = self._generate_model_id()
        model_path = path / f"{model_id}.joblib"
        dump(self._pipeline, model_path)

        # Save metadata
        metadata = {
            "name": self.name,
            "model_type": self.model_type,
            "feature_columns": self.feature_columns,
            "random_state": self.random_state,
            "is_fitted": self._is_fitted,
            "training_result": self._training_result.to_dict() if self._training_result else None,
            "feature_importances": self._feature_importances,
        }
        metadata_path = path / f"{model_id}.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        logger.info("Model saved", path=str(model_path))
        return str(model_path)

    @classmethod
    def load(cls, path: Union[str, Path]) -> "MLFactor":
        """Load a trained model from disk.

        Args:
            path: Path to the .joblib model file.

        Returns:
            Loaded MLFactor instance.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Model file not found: {path}")

        # Load metadata
        metadata_path = path.with_suffix(".json")
        metadata: dict[str, Any] = {}
        if metadata_path.exists():
            with open(metadata_path) as f:
                metadata = json.load(f)

        # Reconstruct factor
        factor = cls(
            name=metadata.get("name", path.stem),
            model_type=metadata.get("model_type", "RandomForestClassifier"),
            feature_columns=metadata.get("feature_columns", []),
            random_state=metadata.get("random_state", 42),
        )

        # Load pipeline
        factor._pipeline = load(path)
        factor._is_fitted = metadata.get("is_fitted", True)
        factor._feature_importances = metadata.get("feature_importances", {})

        # Load training result
        tr = metadata.get("training_result")
        if tr:
            factor._training_result = TrainingResult(**tr)

        logger.info("Model loaded", path=str(path), name=factor.name)
        return factor

    def _generate_model_id(self) -> str:
        """Generate a unique model ID based on name and timestamp."""
        raw = f"{self.name}_{datetime.utcnow().isoformat()}"
        short_hash = hashlib.md5(raw.encode()).hexdigest()[:8]
        return f"{self.name}_{short_hash}"

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    @property
    def pipeline(self) -> Optional[Any]:
        return self._pipeline

    @property
    def feature_importances(self) -> dict[str, float]:
        return dict(self._feature_importances)

    @property
    def training_result(self) -> Optional[TrainingResult]:
        return self._training_result


# ---------------------------------------------------------------------------
# Walk-forward optimization
# ---------------------------------------------------------------------------

@dataclass
class WalkForwardSplit:
    """Walk-forward time series cross-validator.

    Splits time series data into sequential train/test windows.
    """

    train_size: int = 252   # ~1 year of daily data
    test_size: int = 63     # ~3 months
    step: int = 21          # ~1 month step

    def split(
        self,
        X: pd.DataFrame,
        y: Optional[pd.Series] = None,
    ) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        """Generate train/test index pairs.

        Args:
            X: Feature DataFrame (index used as ordering reference).
            y: Target (unused, kept for sklearn compatibility).

        Yields:
            (train_indices, test_indices) tuples.
        """
        n = len(X)
        start = 0

        while start + self.train_size + self.test_size <= n:
            train_end = start + self.train_size
            test_end = train_end + self.test_size

            train_idx = np.arange(start, train_end)
            test_idx = np.arange(train_end, test_end)

            yield train_idx, test_idx

            start += self.step

    def get_n_splits(self, X=None, y=None, groups=None) -> int:
        """Return the number of splitting iterations."""
        n = len(X) if X is not None else 0
        if n == 0:
            return 0
        max_starts = max(0, n - self.train_size - self.test_size)
        return max_starts // self.step + 1


class WalkForwardOptimizer:
    """Walk-forward optimization framework for ML factors.

    Performs rolling window training and evaluation to simulate
    out-of-sample performance over time.
    """

    def __init__(
        self,
        factor: MLFactor,
        split: Optional[WalkForwardSplit] = None,
    ) -> None:
        self.factor = factor
        self.split = split or WalkForwardSplit()
        self.results: list[TrainingResult] = []

    def evaluate(
        self,
        data: pd.DataFrame,
        target_column: str = "target",
        features: Optional[list[str]] = None,
    ) -> list[TrainingResult]:
        """Run walk-forward evaluation.

        Args:
            data: Full time series DataFrame.
            target_column: Column name for the target variable.
            features: Optional list of feature column names.

        Returns:
            List of TrainingResult for each window.
        """
        if features:
            self.factor.feature_columns = features

        X = data.drop(columns=[target_column]) if target_column in data.columns else data
        y = data[target_column] if target_column in data.columns else None

        if y is None:
            raise ValueError(f"Target column '{target_column}' not found in data")

        self.results.clear()

        for fold, (train_idx, test_idx) in enumerate(self.split.split(X, y)):
            logger.info(
                "Walk-forward fold %d/%d",
                fold + 1,
                self.split.get_n_splits(X),
            )

            X_train = X.iloc[train_idx]
            y_train = y.iloc[train_idx]
            X_test = X.iloc[test_idx]
            y_test = y.iloc[test_idx]

            # Train
            self.factor.fit(X_train, y_train)

            # Evaluate on test
            test_preds = self.factor.predict(X_test)
            from sklearn.metrics import accuracy_score, r2_score

            estimator = self.factor._pipeline.named_steps["estimator"]
            if hasattr(estimator, "predict_proba") or hasattr(estimator, "decision_function"):
                score = accuracy_score(y_test, test_preds)
            else:
                score = r2_score(y_test, test_preds)

            result = self.factor.training_result
            if result:
                result.test_score = score
                result.model_id = (
                    f"{self.factor.name}_fold{fold}_"
                    f"{datetime.utcnow().strftime('%Y%m%d')}"
                )
                self.results.append(result)

        # Summary
        if self.results:
            test_scores = [r.test_score for r in self.results]
            logger.info(
                "Walk-forward complete",
                num_folds=len(self.results),
                mean_test_score=round(np.mean(test_scores), 4),
                std_test_score=round(np.std(test_scores), 4),
                min_test_score=round(min(test_scores), 4),
                max_test_score=round(max(test_scores), 4),
            )

        return self.results

    def get_summary(self) -> dict[str, Any]:
        """Get walk-forward evaluation summary."""
        if not self.results:
            return {"status": "no_results"}

        test_scores = [r.test_score for r in self.results]

        return {
            "num_folds": len(self.results),
            "mean_test_score": float(np.mean(test_scores)),
            "std_test_score": float(np.std(test_scores)),
            "min_test_score": float(min(test_scores)),
            "max_test_score": float(max(test_scores)),
            "median_test_score": float(np.median(test_scores)),
            "scores": test_scores,
            "factor_name": self.factor.name,
            "model_type": self.factor.model_type,
        }


# ---------------------------------------------------------------------------
# In-memory model registry (simple store for the API)
# ---------------------------------------------------------------------------

class MLFactorRegistry:
    """Simple in-memory registry for trained ML models.

    Maps model_id -> (MLFactor, TrainingResult).
    """

    def __init__(self) -> None:
        self._models: dict[str, MLFactor] = {}
        self._results: dict[str, TrainingResult] = {}
        self._save_dir: Optional[Path] = None

    def set_save_dir(self, path: Union[str, Path]) -> None:
        self._save_dir = Path(path)
        self._save_dir.mkdir(parents=True, exist_ok=True)

    def register(
        self,
        factor: MLFactor,
        result: Optional[TrainingResult] = None,
    ) -> str:
        """Register a trained model and persist it.

        Args:
            factor: Trained MLFactor instance.
            result: Optional training result (extracted from factor if None).

        Returns:
            model_id string.
        """
        if not factor.is_fitted:
            raise ValueError("Cannot register an unfitted model.")

        tr = result or factor.training_result
        if tr is None and factor.training_result is not None:
            tr = factor.training_result

        model_id = tr.model_id if tr else factor._generate_model_id()

        # Persist
        if self._save_dir:
            path = factor.save(self._save_dir)
            if tr:
                tr.path = path

        self._models[model_id] = factor
        if tr:
            self._results[model_id] = tr

        logger.info("Model registered", model_id=model_id, name=factor.name)
        return model_id

    def get(self, model_id: str) -> Optional[MLFactor]:
        return self._models.get(model_id)

    def get_result(self, model_id: str) -> Optional[TrainingResult]:
        return self._results.get(model_id)

    def list_models(self) -> list[dict[str, Any]]:
        return [
            result.to_dict() for result in self._results.values()
        ]

    def remove(self, model_id: str) -> bool:
        if model_id in self._models:
            del self._models[model_id]
            self._results.pop(model_id, None)
            return True
        return False

    def clear(self) -> None:
        self._models.clear()
        self._results.clear()


# Global singleton registry
registry = MLFactorRegistry()
"""ML Factor API routes.

Provides endpoints for training, predicting, and managing
machine learning factor models.
"""

from typing import Any, Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query, status

from ist.api.schemas.base import BaseResponse
from ist.core.logging import get_logger
from ist.risk.ml_factors import (
    MLFactor,
    MLFactorRegistry,
    PredictionResult,
    WalkForwardOptimizer,
    WalkForwardSplit,
    registry,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/ml-factors", tags=["ML Factors"])


def _get_registry() -> MLFactorRegistry:
    """Get the global ML factor registry."""
    return registry


# ---------------------------------------------------------------------------
# Train
# ---------------------------------------------------------------------------

@router.post(
    "/train",
    response_model=BaseResponse[dict],
    status_code=status.HTTP_200_OK,
    summary="Train an ML factor model",
    description="Train a machine learning model on historical features and targets",
)
async def train_model(
    request: dict[str, Any],
) -> BaseResponse[dict]:
    """Train a new ML factor model.

    Request body:
    ```json
    {
        "name": "rsi_momentum_ml",
        "model_type": "RandomForestClassifier",
        "model_params": {"n_estimators": 100, "max_depth": 5},
        "feature_columns": ["rsi", "momentum", "volatility"],
        "target_column": "target",
        "data": {
            "features": [...],
            "target": [...]
        }
    }
    ```
    """
    try:
        # Extract parameters
        name = request.get("name", "ml_factor")
        model_type = request.get("model_type", "RandomForestClassifier")
        model_params = request.get("model_params", {})
        feature_columns = request.get("feature_columns", [])
        target_column = request.get("target_column", "target")
        data = request.get("data")

        if not data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing 'data' field with 'features' and 'target' arrays",
            )

        # Convert to DataFrame
        features = data.get("features", [])
        target = data.get("target", [])

        if not features or not target:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="'features' and 'target' arrays must not be empty",
            )

        X = pd.DataFrame(features)
        y = pd.Series(target)

        # Create and train factor
        factor = MLFactor(
            name=name,
            model_type=model_type,
            model_params=model_params,
            feature_columns=feature_columns or list(X.columns),
            target_column=target_column,
        )

        factor.fit(X, y)

        # Register model
        reg = _get_registry()
        model_id = reg.register(factor)

        result = factor.training_result
        return BaseResponse(
            success=True,
            data={
                "model_id": model_id,
                "name": name,
                "model_type": model_type,
                "feature_columns": factor.feature_columns,
                "train_score": round(result.train_score, 4) if result else None,
                "test_score": round(result.test_score, 4) if result else None,
                "feature_importances": factor.feature_importances,
                "num_samples": result.num_samples if result else len(X),
            },
            message=f"Model '{name}' trained successfully (ID: {model_id})",
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Model training failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Training failed: {str(exc)}",
        )


# ---------------------------------------------------------------------------
# Predict
# ---------------------------------------------------------------------------

@router.post(
    "/predict",
    response_model=BaseResponse[dict],
    status_code=status.HTTP_200_OK,
    summary="Make predictions with a trained model",
    description="Use a previously trained ML model to make predictions on new data",
)
async def predict(
    request: dict[str, Any],
) -> BaseResponse[dict]:
    """Make predictions using a trained model.

    Request body:
    ```json
    {
        "model_id": "rsi_momentum_ml_a1b2c3d4",
        "data": {
            "features": [...]
        },
        "return_proba": true
    }
    ```
    """
    try:
        model_id = request.get("model_id")
        data = request.get("data")
        return_proba = request.get("return_proba", False)

        if not model_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing 'model_id' field",
            )

        if not data or "features" not in data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing 'data.features' array",
            )

        reg = _get_registry()
        factor = reg.get(model_id)

        if factor is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Model '{model_id}' not found",
            )

        X = pd.DataFrame(data["features"])
        predictions = factor.predict(X).tolist()

        result = PredictionResult(
            model_id=model_id,
            predictions=predictions,
            confidence=0.95,  # Default confidence
            feature_values={},
        )

        if return_proba:
            try:
                proba = factor.predict_proba(X).tolist()
                result.probabilities = proba
            except AttributeError:
                logger.debug(
                    "Model does not support predict_proba", model_id=model_id
                )

        return BaseResponse(
            success=True,
            data=result.to_dict(),
            message=f"Predictions generated for model '{model_id}'",
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Prediction failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prediction failed: {str(exc)}",
        )


# ---------------------------------------------------------------------------
# List models
# ---------------------------------------------------------------------------

@router.get(
    "/models",
    response_model=BaseResponse[list[dict]],
    status_code=status.HTTP_200_OK,
    summary="List all trained models",
    description="Get a list of all registered ML factor models",
)
async def list_models(
    limit: int = Query(20, ge=1, le=100, description="Max number of models to return"),
    offset: int = Query(0, ge=0, description="Number of models to skip"),
) -> BaseResponse[list[dict]]:
    """List all trained ML models."""
    reg = _get_registry()
    all_models = reg.list_models()

    # Sort by training date descending, then paginate
    sorted_models = sorted(
        all_models,
        key=lambda m: m.get("training_date", ""),
        reverse=True,
    )
    paginated = sorted_models[offset:offset + limit]

    return BaseResponse(
        success=True,
        data=paginated,
        message=f"Found {len(paginated)} models (showing {offset+1}-{offset+len(paginated)} of {len(all_models)})",
    )


# ---------------------------------------------------------------------------
# Get model detail
# ---------------------------------------------------------------------------

@router.get(
    "/models/{model_id}",
    response_model=BaseResponse[dict],
    status_code=status.HTTP_200_OK,
    summary="Get model details",
    description="Get detailed information about a specific trained model",
)
async def get_model(
    model_id: str,
) -> BaseResponse[dict]:
    """Get details of a specific model."""
    reg = _get_registry()
    factor = reg.get(model_id)

    if factor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model '{model_id}' not found",
        )

    result = reg.get_result(model_id)

    data = {
        "model_id": model_id,
        "name": factor.name,
        "model_type": factor.model_type,
        "feature_columns": factor.feature_columns,
        "is_fitted": factor.is_fitted,
        "feature_importances": factor.feature_importances,
    }

    if result:
        data["training_result"] = result.to_dict()

    return BaseResponse(
        success=True,
        data=data,
        message=f"Details for model '{model_id}'",
    )


# ---------------------------------------------------------------------------
# Walk-forward optimization
# ---------------------------------------------------------------------------

@router.post(
    "/walk-forward",
    response_model=BaseResponse[dict],
    status_code=status.HTTP_200_OK,
    summary="Run walk-forward optimization",
    description="Perform walk-forward (rolling window) training and evaluation",
)
async def walk_forward_optimize(
    request: dict[str, Any],
) -> BaseResponse[dict]:
    """Run walk-forward optimization.

    Request body:
    ```json
    {
        "name": "rsi_momentum_ml",
        "model_type": "RandomForestClassifier",
        "model_params": {"n_estimators": 100},
        "feature_columns": ["rsi", "momentum"],
        "target_column": "target",
        "data": {...},
        "walk_forward": {
            "train_size": 252,
            "test_size": 63,
            "step": 21
        }
    }
    ```
    """
    try:
        name = request.get("name", "ml_factor")
        model_type = request.get("model_type", "RandomForestClassifier")
        model_params = request.get("model_params", {})
        feature_columns = request.get("feature_columns", [])
        target_column = request.get("target_column", "target")
        data = request.get("data")
        wf_config = request.get("walk_forward", {})

        if not data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing 'data' field",
            )

        df = pd.DataFrame(data)

        # Create split configuration
        split = WalkForwardSplit(
            train_size=wf_config.get("train_size", 252),
            test_size=wf_config.get("test_size", 63),
            step=wf_config.get("step", 21),
        )

        # Create factor and optimizer
        factor = MLFactor(
            name=name,
            model_type=model_type,
            model_params=model_params,
            feature_columns=feature_columns,
            target_column=target_column,
        )

        optimizer = WalkForwardOptimizer(factor, split=split)
        results = optimizer.evaluate(df, target_column=target_column)

        # Register the best model
        reg = _get_registry()
        best_result = max(results, key=lambda r: r.test_score) if results else None
        best_model_id = None
        if best_result:
            best_model_id = reg.register(factor, best_result)

        return BaseResponse(
            success=True,
            data={
                "summary": optimizer.get_summary(),
                "best_model_id": best_model_id,
                "num_folds": len(results),
                "results": [r.to_dict() for r in results],
            },
            message=f"Walk-forward optimization completed with {len(results)} folds",
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Walk-forward optimization failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Walk-forward optimization failed: {str(exc)}",
        )


# ---------------------------------------------------------------------------
# Delete model
# ---------------------------------------------------------------------------

@router.delete(
    "/models/{model_id}",
    response_model=BaseResponse[dict],
    status_code=status.HTTP_200_OK,
    summary="Delete a trained model",
    description="Remove a trained model from the registry",
)
async def delete_model(
    model_id: str,
) -> BaseResponse[dict]:
    """Delete a trained model."""
    reg = _get_registry()
    removed = reg.remove(model_id)

    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model '{model_id}' not found",
        )

    return BaseResponse(
        success=True,
        data={"model_id": model_id},
        message=f"Model '{model_id}' deleted",
    )
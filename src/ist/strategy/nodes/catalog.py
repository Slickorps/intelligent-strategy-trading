"""Catalog of strategy node types for editors and tooling.

Provides a curated, editor-friendly description of every node type in
:attr:`ist.strategy.graph.StrategyGraph.NODE_TYPE_MAP`, including parameter
metadata plus the inputs/outputs derived from the node implementation so the
catalog never drifts from the actual nodes.
"""

import copy
from typing import Any

from ist.strategy.graph import StrategyGraph

NODE_CATALOG: dict[str, dict[str, Any]] = {
    "DataSourceNode": {
        "label": "Data Source",
        "category": "DATA_SOURCE",
        "description": "Loads OHLCV bars for a single symbol from the data provider.",
        "params": [
            {"name": "symbol", "type": "str", "default": "EURUSD"},
            {"name": "timeframe", "type": "str", "default": "1h"},
        ],
    },
    "MultiDataSourceNode": {
        "label": "Multi Data Source",
        "category": "DATA_SOURCE",
        "description": "Loads bars for several symbols simultaneously.",
        "params": [
            {"name": "symbols", "type": "list", "default": ["EURUSD"]},
            {"name": "timeframe", "type": "str", "default": "1h"},
        ],
    },
    "DataFilterNode": {
        "label": "Data Filter",
        "category": "TRANSFORM",
        "description": "Smooths or filters incoming data and reports the trend.",
        "params": [
            {
                "name": "filter_type",
                "type": "str",
                "default": "sma",
                "options": ["sma", "range"],
            },
            {"name": "period", "type": "int", "default": 14, "min": 1},
        ],
    },
    "IndicatorNode": {
        "label": "Indicator",
        "category": "INDICATOR",
        "description": "Computes a technical indicator from a price stream.",
        "params": [
            {
                "name": "indicator",
                "type": "str",
                "default": "SMA",
                "options": ["SMA", "EMA", "RSI", "MACD", "ATR", "BollingerBands"],
            },
            {"name": "period", "type": "int", "default": 14, "min": 1},
            {"name": "period2", "type": "int", "default": 26, "min": 1},
            {"name": "period3", "type": "int", "default": 9, "min": 1},
        ],
    },
    "ConditionNode": {
        "label": "Condition",
        "category": "CONDITION",
        "description": "Evaluates a comparison or crossover between two values.",
        "params": [
            {
                "name": "condition",
                "type": "str",
                "default": "cross_above",
                "options": [
                    "cross_above", "cross_below", "above", "below",
                    "equal", "between",
                ],
            },
            {"name": "threshold", "type": "float", "default": None},
            {"name": "lower_threshold", "type": "float", "default": None},
            {"name": "upper_threshold", "type": "float", "default": None},
        ],
    },
    "LogicGateNode": {
        "label": "Logic Gate",
        "category": "CONDITION",
        "description": "Combines several boolean signals with a logic gate.",
        "params": [
            {
                "name": "gate_type",
                "type": "str",
                "default": "AND",
                "options": ["AND", "OR", "NOT", "XOR", "NAND"],
            },
            {"name": "min_inputs", "type": "int", "default": 2, "min": 1},
        ],
    },
    "ThresholdNode": {
        "label": "Threshold",
        "category": "CONDITION",
        "description": "Classifies a value against a set of thresholds/levels.",
        "params": [
            {"name": "levels", "type": "list", "default": [30, 50, 70]},
            {"name": "mode", "type": "str", "default": "single"},
        ],
    },
    "ActionNode": {
        "label": "Action",
        "category": "ACTION",
        "description": "Emits an order request when triggered.",
        "params": [
            {
                "name": "action",
                "type": "str",
                "default": "buy",
                "options": ["buy", "sell", "close", "rebalance"],
            },
            {"name": "size_pct", "type": "float", "default": 0.05, "min": 0.0, "max": 1.0},
            {
                "name": "order_type",
                "type": "str",
                "default": "market",
                "options": ["market", "limit", "stop", "stop_limit"],
            },
            {
                "name": "time_in_force",
                "type": "str",
                "default": "GTC",
                "options": ["GTC", "IOC", "FOK"],
            },
            {"name": "symbol", "type": "str", "default": "EURUSD"},
        ],
    },
    "RebalanceNode": {
        "label": "Rebalance",
        "category": "ACTION",
        "description": "Computes rebalancing orders from target portfolio weights.",
        "params": [
            {"name": "target_weights", "type": "dict", "default": {}},
            {"name": "threshold_pct", "type": "float", "default": 3.0},
            {"name": "max_deviation", "type": "float", "default": 10.0},
        ],
    },
    "TrailingStopNode": {
        "label": "Trailing Stop",
        "category": "ACTION",
        "description": "Tracks a trailing stop and signals when to exit.",
        "params": [
            {"name": "trail_pct", "type": "float", "default": 3.0},
            {"name": "activation_pct", "type": "float", "default": None},
            {"name": "symbol", "type": "str", "default": "EURUSD"},
        ],
    },
    "RiskNode": {
        "label": "Risk Check",
        "category": "RISK",
        "description": "Approves or rejects a signal against risk limits.",
        "params": [
            {"name": "max_position_pct", "type": "float", "default": 0.10},
            {"name": "max_daily_loss", "type": "float", "default": None},
            {"name": "correlation_limit", "type": "float", "default": 0.8},
            {"name": "volatility_cap", "type": "float", "default": 0.5},
            {"name": "volatility_adjustment", "type": "bool", "default": True},
        ],
    },
    "DrawdownProtectionNode": {
        "label": "Drawdown Protection",
        "category": "RISK",
        "description": "Reduces exposure or halts trading on excessive drawdown.",
        "params": [
            {"name": "max_drawdown_pct", "type": "float", "default": 5.0},
            {
                "name": "action",
                "type": "str",
                "default": "reduce_size",
                "options": ["reduce_size", "stop_trading", "hedge"],
            },
            {"name": "reduction_factor", "type": "float", "default": 0.5},
        ],
    },
}


def default_params(type_name: str) -> dict[str, Any]:
    """Return a fresh copy of the default parameters for a node type."""
    meta = NODE_CATALOG.get(type_name, {})
    return {
        param["name"]: copy.deepcopy(param.get("default"))
        for param in meta.get("params", [])
    }


def build_node_catalog() -> list[dict[str, Any]]:
    """Build the editor catalog, deriving inputs/outputs from node classes."""
    catalog: list[dict[str, Any]] = []

    for type_name, meta in NODE_CATALOG.items():
        node_cls = StrategyGraph.NODE_TYPE_MAP.get(type_name)
        if node_cls is None:
            continue

        node = node_cls("__catalog__", default_params(type_name))

        catalog.append({
            "type": type_name,
            "label": meta["label"],
            "category": meta["category"],
            "description": meta.get("description", ""),
            "params": copy.deepcopy(meta.get("params", [])),
            "inputs": [
                {
                    "name": name,
                    "type": slot.data_type,
                    "required": slot.required,
                }
                for name, slot in node.inputs.items()
            ],
            "outputs": [
                {"name": name, "type": slot.data_type}
                for name, slot in node.outputs.items()
            ],
        })

    return catalog

"""Unit tests for strategy node graph components.

Covers data source nodes, indicator nodes, logic/condition nodes,
action nodes, and risk nodes.
"""

from datetime import datetime

import pytest

from ist.core.exceptions import NodeError
from ist.strategy.nodes.action_nodes import (
    ActionNode,
    RebalanceNode,
    TrailingStopNode,
)
from ist.strategy.nodes.base import (
    NodeExecutionContext,
    NodeInput,
    NodeOutput,
    NodeState,
    NodeType,
    StrategyNode,
)
from ist.strategy.nodes.data_nodes import (
    DataFilterNode,
    DataSourceNode,
    MultiDataSourceNode,
)
from ist.strategy.nodes.indicator_nodes import IndicatorNode
from ist.strategy.nodes.logic_nodes import (
    ConditionNode,
    LogicGateNode,
    ThresholdNode,
)
from ist.strategy.nodes.risk_nodes import (
    DrawdownProtectionNode,
    RiskNode,
)


def make_context(bar_data=None, portfolio=None, custom=None) -> NodeExecutionContext:
    """Create an execution context for node tests."""
    return NodeExecutionContext(
        timestamp=datetime.utcnow(),
        bar_data=bar_data,
        portfolio_state=portfolio,
        custom_data=custom or {},
    )


class FakeNode(StrategyNode):
    """Minimal concrete node for testing the base class."""

    def __init__(
        self, node_id: str = "fake",
        node_type: NodeType = NodeType.INDICATOR,
        params: dict | None = None,
    ) -> None:
        super().__init__(node_id, node_type, params)

    def _setup_inputs(self) -> None:
        self.inputs["in1"] = NodeInput("in1", "float", required=True)

    def _setup_outputs(self) -> None:
        self.outputs["out1"] = NodeOutput("out1", "float")

    def execute(self, context: NodeExecutionContext) -> bool:
        return True


class TestStrategyNodeBase:
    def test_params_default_empty(self) -> None:
        assert FakeNode().params == {}

    def test_set_get_input(self) -> None:
        node = FakeNode()
        node.set_input("in1", 5.0)
        assert node.get_input("in1") == 5.0

    def test_set_input_unknown_raises(self) -> None:
        node = FakeNode()
        with pytest.raises(NodeError, match="not found"):
            node.set_input("missing", 1.0)

    def test_get_input_unknown_raises(self) -> None:
        node = FakeNode()
        with pytest.raises(NodeError, match="not found"):
            node.get_input("missing")

    def test_set_output_unknown_raises(self) -> None:
        node = FakeNode()
        with pytest.raises(NodeError, match="not found"):
            node.set_output("missing", 1.0)

    def test_reset_clears_state_and_values(self) -> None:
        node = FakeNode()
        node.set_input("in1", 5.0)
        node.set_output("out1", 3.0)
        node.state = NodeState.COMPLETED

        node.reset()

        assert node.state == NodeState.IDLE
        assert node.error_message is None
        assert node.get_input("in1") is None
        assert node.get_output("out1") is None

    def test_to_dict(self) -> None:
        node = FakeNode("n1")
        d = node.to_dict()
        assert d["id"] == "n1"
        assert d["type"] == "INDICATOR"
        assert "inputs" in d
        assert "outputs" in d
        assert d["state"] == "IDLE"


class TestDataSourceNode:
    def test_defaults(self) -> None:
        node = DataSourceNode("ds", {})
        assert node.node_type == NodeType.DATA_SOURCE
        assert node.symbol == "EURUSD"
        assert node.timeframe == "1h"
        assert set(node.outputs) == {"bar", "open", "high", "low", "close", "volume"}

    def test_custom_params(self) -> None:
        node = DataSourceNode("ds", {"symbol": "BTCUSD", "timeframe": "1d"})
        assert node.symbol == "BTCUSD"
        assert node.timeframe == "1d"

    def test_execute_extracts_bar_data(self) -> None:
        node = DataSourceNode("ds", {})
        bar = {"open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05, "volume": 100}
        ctx = make_context(bar_data=bar)

        assert node.execute(ctx) is True
        assert node.get_output("bar") == bar
        assert node.get_output("open") == 1.0
        assert node.get_output("close") == 1.05
        assert node.get_output("volume") == 100

    def test_execute_missing_keys_default_zero(self) -> None:
        node = DataSourceNode("ds", {})
        assert node.execute(make_context(bar_data={"close": 1.0})) is True
        assert node.get_output("high") == 0.0

    def test_execute_no_bar_data_returns_false(self) -> None:
        node = DataSourceNode("ds", {})
        assert node.execute(make_context()) is False


class TestMultiDataSourceNode:
    def test_defaults(self) -> None:
        node = MultiDataSourceNode("mds", {})
        assert node.symbols == ["EURUSD"]
        assert "EURUSD_close" in node.outputs
        assert "data_by_symbol" in node.outputs

    def test_outputs_per_symbol(self) -> None:
        node = MultiDataSourceNode("mds", {"symbols": ["EURUSD", "GBPUSD"]})
        assert "EURUSD_close" in node.outputs
        assert "GBPUSD_close" in node.outputs

    def test_execute_reads_custom_data(self) -> None:
        node = MultiDataSourceNode("mds", {"symbols": ["EURUSD", "GBPUSD"]})
        multi = {
            "multi_bars": {
                "EURUSD": {"close": 1.1},
                "GBPUSD": {"close": 1.3},
            },
        }
        ctx = make_context(custom=multi)

        assert node.execute(ctx) is True
        assert node.get_output("symbol_list") == ["EURUSD", "GBPUSD"]
        assert node.get_output("EURUSD_close") == 1.1
        assert node.get_output("GBPUSD_close") == 1.3

    def test_execute_missing_symbol_defaults_zero(self) -> None:
        node = MultiDataSourceNode("mds", {"symbols": ["EURUSD"]})
        assert node.execute(make_context()) is True
        assert node.get_output("EURUSD_close") == 0.0
        assert node.get_output("data_by_symbol") == {}


class TestDataFilterNode:
    def test_defaults(self) -> None:
        node = DataFilterNode("f", {})
        assert node.node_type == NodeType.TRANSFORM
        assert node.filter_type == "sma"
        assert node.period == 14

    def test_execute_insufficient_history_returns_data(self) -> None:
        node = DataFilterNode("f", {"period": 5})
        node.set_input("data", 100.0)
        node.set_input("historical", [1.0, 2.0])

        assert node.execute(make_context()) is True
        assert node.get_output("filtered") == 100.0
        assert node.get_output("trend") == "neutral"

    def test_execute_sma_averages_history(self) -> None:
        node = DataFilterNode("f", {"period": 3})
        node.set_input("data", 10.0)
        node.set_input("historical", [1.0, 2.0, 3.0])

        assert node.execute(make_context()) is True
        assert node.get_output("filtered") == pytest.approx(2.0)
        assert node.get_output("trend") == "down"

    def test_execute_trend_up(self) -> None:
        node = DataFilterNode("f", {"period": 3})
        node.set_input("data", 1.0)
        node.set_input("historical", [5.0, 6.0, 7.0])
        node.execute(make_context())
        assert node.get_output("filtered") == pytest.approx(6.0)
        assert node.get_output("trend") == "up"

    def test_execute_no_data_returns_false(self) -> None:
        node = DataFilterNode("f", {})
        node.set_input("data", None)
        assert node.execute(make_context()) is False


class TestIndicatorNode:
    def test_defaults(self) -> None:
        node = IndicatorNode("i", {})
        assert node.node_type == NodeType.INDICATOR
        assert node.indicator == "SMA"
        assert node.period == 14

    def test_sma_outputs(self) -> None:
        node = IndicatorNode("i", {"indicator": "SMA"})
        assert set(node.outputs) == {"value", "slope"}

    def test_rsi_outputs(self) -> None:
        node = IndicatorNode("i", {"indicator": "RSI"})
        assert set(node.outputs) == {"value", "overbought", "oversold"}

    def test_macd_outputs(self) -> None:
        node = IndicatorNode("i", {"indicator": "MACD"})
        assert set(node.outputs) == {"macd", "signal", "histogram"}

    def test_unknown_indicator_builds_none(self) -> None:
        node = IndicatorNode("i", {"indicator": "FOO"})
        assert node._indicator_instance is None

    def test_execute_no_price_returns_false(self) -> None:
        node = IndicatorNode("i", {"indicator": "SMA"})
        assert node.execute(make_context()) is False

    def test_execute_sma_calculates_value(self) -> None:
        node = IndicatorNode("i", {"indicator": "SMA", "period": 2})
        ctx = make_context()

        node.set_input("price", 1.0)
        assert node.execute(ctx) is True
        node.set_input("price", 3.0)
        assert node.execute(ctx) is True

        assert node.get_output("value") == pytest.approx(2.0)
        assert node.get_output("slope") == pytest.approx(200.0)

    def test_execute_rsi_returns_boolean_flags(self) -> None:
        node = IndicatorNode("i", {"indicator": "RSI", "period": 2})
        ctx = make_context()
        for price in [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0]:
            node.set_input("price", price)
            assert node.execute(ctx) is True
        assert isinstance(node.get_output("overbought"), bool)
        assert isinstance(node.get_output("oversold"), bool)

    def test_execute_unknown_indicator_returns_zero(self) -> None:
        node = IndicatorNode("i", {"indicator": "FOO"})
        node.set_input("price", 100.0)
        assert node.execute(make_context()) is True
        assert node.get_output("value") == 0.0

    def test_reset_clears_history(self) -> None:
        node = IndicatorNode("i", {"indicator": "SMA", "period": 2})
        ctx = make_context()
        node.set_input("price", 1.0)
        node.execute(ctx)
        assert len(node._history) == 1

        node.reset()

        assert node._history == []
        assert node.state == NodeState.IDLE


class TestConditionNode:
    def _exec(self, node: ConditionNode, a, b=None) -> bool:
        node.set_input("value_a", a)
        if b is not None:
            node.set_input("value_b", b)
        return node.execute(make_context())

    def test_above(self) -> None:
        node = ConditionNode("c", {"condition": "above"})
        assert self._exec(node, 1.1, 1.0) is True
        assert node.get_output("triggered") is True
        assert node.get_output("direction") == "up"
        assert node.get_output("strength") == pytest.approx(0.1)

    def test_above_false(self) -> None:
        node = ConditionNode("c", {"condition": "above"})
        self._exec(node, 1.0, 1.1)
        assert node.get_output("triggered") is False

    def test_below(self) -> None:
        node = ConditionNode("c", {"condition": "below"})
        self._exec(node, 0.9, 1.0)
        assert node.get_output("triggered") is True
        assert node.get_output("direction") == "down"

    def test_equal(self) -> None:
        node = ConditionNode("c", {"condition": "equal"})
        self._exec(node, 1.0, 1.0)
        assert node.get_output("triggered") is True

    def test_threshold_fallback(self) -> None:
        node = ConditionNode("c", {"condition": "above", "threshold": 1.0})
        self._exec(node, 1.1)
        assert node.get_output("triggered") is True

    def test_value_a_none_returns_false(self) -> None:
        node = ConditionNode("c", {"condition": "above"})
        node.set_input("value_a", None)
        assert node.execute(make_context()) is False

    def test_cross_above(self) -> None:
        node = ConditionNode("c", {"condition": "cross_above"})
        assert self._exec(node, 0.9, 1.0) is True
        assert node.get_output("triggered") is False
        self._exec(node, 1.1, 1.0)
        assert node.get_output("triggered") is True
        assert node.get_output("direction") == "up"

    def test_cross_below(self) -> None:
        node = ConditionNode("c", {"condition": "cross_below"})
        self._exec(node, 1.1, 1.0)
        self._exec(node, 0.9, 1.0)
        assert node.get_output("triggered") is True
        assert node.get_output("direction") == "down"

    def test_between(self) -> None:
        node = ConditionNode(
            "c",
            {
                "condition": "between",
                "lower_threshold": 10,
                "upper_threshold": 20,
            },
        )
        self._exec(node, 15)
        assert node.get_output("triggered") is True

    def test_reset_clears_previous_values(self) -> None:
        node = ConditionNode("c", {"condition": "cross_above"})
        self._exec(node, 1.0, 1.0)
        assert node._prev_value_a is not None
        node.reset()
        assert node._prev_value_a is None
        assert node._prev_value_b is None


class TestLogicGateNode:
    def test_and_true(self) -> None:
        node = LogicGateNode("g", {"gate_type": "AND"})
        node.set_input("input_0", True)
        node.set_input("input_1", True)
        assert node.execute(make_context()) is True
        assert node.get_output("result") is True
        assert node.get_output("input_count") == 2
        assert node.get_output("true_count") == 2

    def test_and_one_false(self) -> None:
        node = LogicGateNode("g", {"gate_type": "AND"})
        node.set_input("input_0", True)
        node.set_input("input_1", False)
        node.execute(make_context())
        assert node.get_output("result") is False

    def test_and_min_inputs_not_met(self) -> None:
        node = LogicGateNode("g", {"gate_type": "AND", "min_inputs": 3})
        node.set_input("input_0", True)
        node.set_input("input_1", True)
        node.execute(make_context())
        assert node.get_output("result") is False

    def test_or(self) -> None:
        node = LogicGateNode("g", {"gate_type": "OR"})
        node.set_input("input_0", False)
        node.set_input("input_1", True)
        node.execute(make_context())
        assert node.get_output("result") is True

    def test_not(self) -> None:
        node = LogicGateNode("g", {"gate_type": "NOT"})
        node.set_input("input_0", True)
        node.execute(make_context())
        assert node.get_output("result") is False

    def test_xor(self) -> None:
        node = LogicGateNode("g", {"gate_type": "XOR"})
        node.set_input("input_0", True)
        node.set_input("input_1", False)
        node.execute(make_context())
        assert node.get_output("result") is True

    def test_nand(self) -> None:
        node = LogicGateNode("g", {"gate_type": "NAND"})
        node.set_input("input_0", True)
        node.set_input("input_1", True)
        node.execute(make_context())
        assert node.get_output("result") is False

    def test_no_inputs_returns_false(self) -> None:
        node = LogicGateNode("g", {"gate_type": "AND"})
        node.execute(make_context())
        assert node.get_output("result") is False
        assert node.get_output("input_count") == 0


class TestThresholdNode:
    def test_defaults(self) -> None:
        node = ThresholdNode("t", {})
        assert node.levels == [30, 50, 70]
        assert node.mode == "single"

    def test_low_value(self) -> None:
        node = ThresholdNode("t", {})
        node.set_input("value", 20)
        assert node.execute(make_context()) is True
        assert node.get_output("level") == 0
        assert node.get_output("level_name") == "low"
        assert node.get_output("above_30") is False

    def test_mid_value(self) -> None:
        node = ThresholdNode("t", {})
        node.set_input("value", 40)
        node.execute(make_context())
        assert node.get_output("level") == 1
        assert node.get_output("level_name") == "medium"
        assert node.get_output("above_30") is True
        assert node.get_output("above_50") is False

    def test_high_value(self) -> None:
        node = ThresholdNode("t", {})
        node.set_input("value", 60)
        node.execute(make_context())
        assert node.get_output("level") == 2
        assert node.get_output("level_name") == "high"

    def test_extreme_value(self) -> None:
        node = ThresholdNode("t", {})
        node.set_input("value", 90)
        node.execute(make_context())
        assert node.get_output("level") == 3
        assert node.get_output("level_name") == "extreme"

    def test_normalized_clamped(self) -> None:
        node = ThresholdNode("t", {"levels": [0, 100]})
        node.set_input("value", 200)
        node.execute(make_context())
        assert node.get_output("normalized") == 1.0

    def test_value_none_returns_false(self) -> None:
        node = ThresholdNode("t", {})
        node.set_input("value", None)
        assert node.execute(make_context()) is False


class TestActionNode:
    def test_defaults(self) -> None:
        node = ActionNode("a", {})
        assert node.action == "buy"
        assert node.size_pct == 0.05
        assert node.symbol == "EURUSD"

    def test_execute_without_trigger_executes(self) -> None:
        node = ActionNode("a", {"action": "buy", "size_pct": 0.1})
        assert node.execute(make_context()) is True
        assert node.get_output("action_taken") is True
        order = node.get_output("order_request")
        assert order["action"] == "buy"
        assert order["symbol"] == "EURUSD"
        assert order["side"] == "buy"
        assert order["size_pct"] == pytest.approx(0.1)
        assert "timestamp" in order

    def test_execute_trigger_false_skips(self) -> None:
        node = ActionNode("a", {})
        node.set_input("trigger", False)
        assert node.execute(make_context()) is True
        assert node.get_output("action_taken") is False

    def test_signal_strength_adjusts_size(self) -> None:
        node = ActionNode("a", {"size_pct": 0.1})
        node.set_input("signal_strength", 0.5)
        node.execute(make_context())
        assert node.get_output("position_size") == pytest.approx(0.05)
        assert node.get_output("order_request")["size_pct"] == pytest.approx(0.05)

    def test_sell_side(self) -> None:
        node = ActionNode("a", {"action": "sell"})
        node.execute(make_context())
        assert node.get_output("order_request")["side"] == "sell"

    def test_close_side(self) -> None:
        node = ActionNode("a", {"action": "close"})
        node.execute(make_context())
        assert node.get_output("order_request")["side"] == "close"

    def test_optional_prices_included(self) -> None:
        node = ActionNode("a", {})
        node.set_input("target_price", 1.2)
        node.set_input("stop_price", 1.0)
        node.execute(make_context())
        order = node.get_output("order_request")
        assert order["target_price"] == pytest.approx(1.2)
        assert order["stop_price"] == pytest.approx(1.0)


class TestRebalanceNode:
    def _run(self, node: RebalanceNode, current_weights: dict) -> bool:
        node.set_input("current_weights", current_weights)
        return node.execute(make_context())

    def test_no_deviation_no_rebalance(self) -> None:
        node = RebalanceNode("r", {"target_weights": {"A": 0.5, "B": 0.5}})
        self._run(node, {"A": 0.5, "B": 0.5})
        assert node.get_output("needs_rebalance") is False
        assert node.get_output("rebalance_orders") == []
        assert node.get_output("total_turnover") == 0.0

    def test_deviation_triggers_orders(self) -> None:
        node = RebalanceNode(
            "r", {"target_weights": {"A": 0.6, "B": 0.4}, "threshold_pct": 3.0},
        )
        self._run(node, {"A": 0.5, "B": 0.5})

        assert node.get_output("needs_rebalance") is True
        orders = node.get_output("rebalance_orders")
        assert len(orders) == 2
        by_symbol = {o["symbol"]: o for o in orders}
        assert by_symbol["A"]["side"] == "buy"
        assert by_symbol["B"]["side"] == "sell"
        assert node.get_output("total_turnover") == pytest.approx(0.2)

    def test_trigger_false_skips(self) -> None:
        node = RebalanceNode("r", {"target_weights": {"A": 0.6}})
        node.set_input("trigger", False)
        node.execute(make_context())
        assert node.get_output("needs_rebalance") is False

    def test_deviations_reported(self) -> None:
        node = RebalanceNode("r", {"target_weights": {"A": 0.6}})
        self._run(node, {"A": 0.5})
        deviations = node.get_output("deviations")
        assert deviations["A"]["current"] == 0.5
        assert deviations["A"]["target"] == 0.6
        assert deviations["A"]["deviation_pct"] == pytest.approx(10.0)


class TestTrailingStopNode:
    def _prices(self, node: TrailingStopNode, prices) -> None:
        for price in prices:
            node.set_input("current_price", price)
            node.set_input("position_side", "long")
            node.execute(make_context())

    def test_initial_price_sets_baseline_only(self) -> None:
        node = TrailingStopNode("t", {"trail_pct": 10.0})
        node.set_input("current_price", 100.0)
        node.set_input("position_side", "long")
        assert node.execute(make_context()) is True
        assert node.get_output("stop_price") is None
        assert node.get_output("activated") is True

    def test_new_high_sets_stop(self) -> None:
        node = TrailingStopNode("t", {"trail_pct": 10.0})
        self._prices(node, [100.0, 120.0])
        assert node.get_output("stop_price") == pytest.approx(108.0)

    def test_price_below_stop_triggers_exit(self) -> None:
        node = TrailingStopNode("t", {"trail_pct": 10.0})
        self._prices(node, [100.0, 120.0, 107.0])
        assert node.get_output("should_exit") is True

    def test_no_price_returns_false(self) -> None:
        node = TrailingStopNode("t", {})
        node.set_input("current_price", None)
        node.set_input("position_side", "long")
        assert node.execute(make_context()) is False

    def test_reset_clears_state(self) -> None:
        node = TrailingStopNode("t", {})
        self._prices(node, [100.0, 120.0])
        node.reset()
        assert node._highest_price is None
        assert node._stop_price is None
        assert node._activated is False


class TestRiskNode:
    def _run(self, node: RiskNode, **inputs) -> bool:
        node.set_input("signal", True)
        for key, value in inputs.items():
            node.set_input(key, value)
        return node.execute(make_context())

    def test_approves_within_limits(self) -> None:
        node = RiskNode("risk", {})
        assert self._run(node, position_size=0.05) is True
        assert node.get_output("approved") is True
        assert node.get_output("reject_reason") == ""
        assert node.get_output("adjusted_size") == pytest.approx(0.05)
        assert "position_size" in node.get_output("checks_passed")

    def test_rejects_oversized_position(self) -> None:
        node = RiskNode("risk", {})
        self._run(node, position_size=0.5)
        assert node.get_output("approved") is False
        assert "exceeds limit" in node.get_output("reject_reason")
        assert node.get_output("adjusted_size") == 0.0
        assert node.get_output("risk_score") == 100.0

    def test_rejects_daily_loss(self) -> None:
        node = RiskNode("risk", {"max_daily_loss": 1000.0})
        self._run(node, position_size=0.05, daily_pnl=-2000.0)
        assert node.get_output("approved") is False
        assert "Daily loss" in node.get_output("reject_reason")

    def test_rejects_high_volatility(self) -> None:
        node = RiskNode("risk", {})
        self._run(node, position_size=0.05, atr=80.0, portfolio_value=100.0)
        assert node.get_output("approved") is False
        assert "Volatility" in node.get_output("reject_reason")

    def test_volatility_adjusts_size(self) -> None:
        node = RiskNode("risk", {})
        self._run(node, position_size=0.10, atr=500.0, portfolio_value=100000.0)
        assert node.get_output("approved") is True
        assert node.get_output("adjusted_size") < 0.10

    def test_all_checks_passed(self) -> None:
        node = RiskNode("risk", {"max_daily_loss": 1000.0})
        self._run(node, position_size=0.05, daily_pnl=100.0)
        assert node.get_output("checks_passed") == [
            "position_size", "daily_loss", "volatility",
        ]

    def test_risk_score_capped(self) -> None:
        node = RiskNode("risk", {"max_daily_loss": 1000.0})
        self._run(node, position_size=0.10, daily_pnl=-500.0, atr=600.0)
        score = node.get_output("risk_score")
        assert 0 <= score <= 100


class TestDrawdownProtectionNode:
    def _exec(self, node: DrawdownProtectionNode, dd: float) -> bool:
        node.set_input("current_drawdown", dd)
        return node.execute(make_context())

    def test_not_triggered(self) -> None:
        node = DrawdownProtectionNode("dd", {})
        self._exec(node, 0.01)
        assert node.get_output("triggered") is False
        assert node.get_output("action") == "none"
        assert node.get_output("size_multiplier") == 1.0
        assert node.get_output("urgency") == "normal"

    def test_reduce_size_when_triggered(self) -> None:
        node = DrawdownProtectionNode("dd", {})
        self._exec(node, 0.06)
        assert node.get_output("triggered") is True
        assert node.get_output("action") == "reduce_size"
        assert node.get_output("size_multiplier") < 1.0
        assert node.get_output("urgency") == "medium"

    def test_stop_trading_zeroes_size(self) -> None:
        node = DrawdownProtectionNode("dd", {"action": "stop_trading"})
        self._exec(node, 0.06)
        assert node.get_output("size_multiplier") == 0.0

    def test_urgency_critical(self) -> None:
        node = DrawdownProtectionNode("dd", {})
        self._exec(node, 0.12)
        assert node.get_output("urgency") == "critical"

    def test_none_drawdown_returns_false(self) -> None:
        node = DrawdownProtectionNode("dd", {})
        node.set_input("current_drawdown", None)
        assert node.execute(make_context()) is False

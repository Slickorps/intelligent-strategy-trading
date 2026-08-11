"""Unit tests for strategy graph, executor, and node connections."""
import json
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from ist.core.exceptions import GraphError, ValidationError
from ist.strategy.executor import ExecutionResult, StrategyExecutor
from ist.strategy.graph import NodeConnection, StrategyGraph
from ist.strategy.nodes.base import NodeExecutionContext, NodeState, NodeType, StrategyNode
from ist.strategy.serializer import (
    deserialize_graph,
    graph_from_json,
    graph_to_json,
    migrate_config,
    serialize_graph,
    validate_profile_config,
    validate_strategy_config,
)


class FakeNode(StrategyNode):
    """Minimal node for testing."""

    def __init__(self, node_id: str, params: dict = None) -> None:
        super().__init__(
            node_id=node_id,
            node_type=NodeType.INDICATOR,
            params=params or {},
        )

    def _setup_inputs(self) -> None:
        self.inputs = []
        self.input_names = set()

    def _setup_outputs(self) -> None:
        self.outputs = []
        self.output_names = set()

    def execute(self, context: NodeExecutionContext) -> bool:
        return True

    def to_dict(self) -> dict:
        return {
            "id": self.node_id,
            "type": self.node_type.name,
            "params": self.params,
            "state": self.state.name,
        }


class FakeActionNode(FakeNode):
    def __init__(self, node_id: str, params: dict = None) -> None:
        super().__init__(node_id, params or {})
        self.node_type = NodeType.ACTION


class TestNodeConnection:
    def test_default_connection(self):
        conn = NodeConnection("n1", "n2")
        assert conn.from_node == "n1"
        assert conn.to_node == "n2"
        assert conn.from_output == "value"
        assert conn.to_input == "data"

    def test_custom_connection(self):
        conn = NodeConnection("a", "b", from_output="signal", to_input="price")
        assert conn.from_output == "signal"
        assert conn.to_input == "price"

    def test_to_dict(self):
        conn = NodeConnection("src", "dst", "out", "inp")
        d = conn.to_dict()
        assert d == {"from": "src", "to": "dst", "from_output": "out", "to_input": "inp"}


class TestStrategyGraph:
    @pytest.fixture
    def graph(self):
        return StrategyGraph("test-graph", "Test Strategy")

    def test_create_graph(self, graph):
        assert graph.graph_id == "test-graph"
        assert graph.name == "Test Strategy"
        assert len(graph.get_nodes()) == 0

    def test_add_node(self, graph):
        node = FakeNode("n1")
        graph.add_node(node)
        assert graph.get_node("n1") is node
        assert len(graph.get_nodes()) == 1

    def test_remove_node(self, graph):
        n1 = FakeNode("n1")
        n2 = FakeNode("n2")
        graph.add_node(n1)
        graph.add_node(n2)
        graph.remove_node("n1")
        assert graph.get_node("n1") is None
        assert graph.get_node("n2") is not None

    def test_add_connection_valid(self, graph):
        graph.add_node(FakeNode("n1"))
        graph.add_node(FakeNode("n2"))
        graph.add_connection("n1", "n2")
        assert len(graph._connections) == 1

    def test_add_connection_source_missing(self, graph):
        graph.add_node(FakeNode("n2"))
        with pytest.raises(GraphError, match="Source node"):
            graph.add_connection("n1", "n2")

    def test_add_connection_target_missing(self, graph):
        graph.add_node(FakeNode("n1"))
        with pytest.raises(GraphError, match="Target node"):
            graph.add_connection("n1", "n2")

    def test_validate_empty_graph(self, graph):
        valid, errors = graph.validate()
        assert not valid
        assert any("no nodes" in e for e in errors)

    def test_validate_simple(self, graph):
        from ist.strategy.nodes.data_nodes import DataSourceNode
        from ist.strategy.nodes.action_nodes import ActionNode
        graph.add_node(DataSourceNode("n1", {}))
        graph.add_node(ActionNode("n2", {}))
        graph.add_connection("n1", "n2", from_output="close", to_input="signal_strength")
        valid, errors = graph.validate()
        assert valid, f"Errors: {errors}"

    def test_validate_cycle_detection(self, graph):
        graph.add_node(FakeNode("a"))
        graph.add_node(FakeNode("b"))
        graph.add_node(FakeNode("c"))
        graph.add_connection("a", "b")
        graph.add_connection("b", "c")
        graph.add_connection("c", "a")
        valid, errors = graph.validate()
        assert not valid
        assert any("cycles" in e for e in errors)

    def test_remove_node_removes_connections(self, graph):
        graph.add_node(FakeNode("a"))
        graph.add_node(FakeNode("b"))
        graph.add_node(FakeNode("c"))
        graph.add_connection("a", "b")
        graph.add_connection("b", "c")
        graph.remove_node("b")
        assert len(graph._connections) == 0

    def test_to_dict(self, graph):
        graph.add_node(FakeNode("n1"))
        d = graph.to_dict()
        assert d["graph_id"] == "test-graph"
        assert len(d["nodes"]) == 1
        assert "connections" in d

    def test_from_config_basic(self):
        config = {
            "version": "1.0",
            "name": "Test",
            "nodes": [{"id": "n1", "type": "DataSourceNode", "params": {}}],
            "connections": [],
        }
        g = StrategyGraph.from_config("g1", config)
        assert g.graph_id == "g1"
        assert len(g.get_nodes()) == 1

    def test_from_config_unknown_type_raises(self):
        config = {
            "version": "1.0",
            "nodes": [{"id": "n1", "type": "UnknownType", "params": {}}],
            "connections": [],
        }
        with pytest.raises(GraphError, match="Unknown node type"):
            StrategyGraph.from_config("g1", config)

    def test_execute_invalid_graph_raises(self, graph):
        ctx = NodeExecutionContext(timestamp=datetime.utcnow(), bar_data={})
        with pytest.raises(GraphError, match="Cannot execute invalid graph"):
            graph.execute(ctx)


class TestStrategyExecutor:
    @pytest.fixture
    def executor(self):
        return StrategyExecutor()

    @pytest.fixture
    def valid_graph(self):
        g = StrategyGraph("vg", "Valid")
        g.add_node(FakeActionNode("action1"))
        return g

    def test_initial_state(self, executor):
        assert executor._is_running is False
        assert len(executor._strategies) == 0

    def test_add_strategy_valid(self, executor, valid_graph):
        executor.add_strategy("s1", valid_graph)
        assert "s1" in executor._strategies
        assert executor._strategy_states["s1"]["active"] is False

    def test_add_invalid_strategy_raises(self, executor):
        g = StrategyGraph("iv", "")
        with pytest.raises(ValueError, match="validation failed"):
            executor.add_strategy("s1", g)

    def test_start_stop_strategy(self, executor, valid_graph):
        executor.add_strategy("s1", valid_graph)
        executor.start_strategy("s1")
        assert executor._strategy_states["s1"]["active"] is True
        executor.stop_strategy("s1")
        assert executor._strategy_states["s1"]["active"] is False

    def test_start_missing_strategy_raises(self, executor):
        with pytest.raises(ValueError, match="not found"):
            executor.start_strategy("nonexistent")

    def test_remove_strategy(self, executor, valid_graph):
        executor.add_strategy("s1", valid_graph)
        executor.remove_strategy("s1")
        assert "s1" not in executor._strategies

    def test_execute_all_when_inactive_returns_empty(self, executor, valid_graph):
        executor.add_strategy("s1", valid_graph)
        results = executor.execute_all({})
        assert len(results) == 0

    def test_execute_strategy_not_found(self, executor):
        result = executor.execute_strategy("missing", {})
        assert result.success is False
        assert "not found" in result.error_message

    def test_execute_strategy_not_active(self, executor, valid_graph):
        executor.add_strategy("s1", valid_graph)
        result = executor.execute_strategy("s1", {})
        assert result.success is False
        assert "not active" in result.error_message

    def test_get_strategy_status(self, executor, valid_graph):
        executor.add_strategy("s1", valid_graph)
        status = executor.get_strategy_status("s1")
        assert status is not None
        assert status["execution_count"] == 0

    def test_get_all_status(self, executor, valid_graph):
        executor.add_strategy("s1", valid_graph)
        executor.add_strategy("s2", valid_graph)
        statuses = executor.get_all_status()
        assert len(statuses) == 2

    def test_reset(self, executor, valid_graph):
        executor.add_strategy("s1", valid_graph)
        executor.start_strategy("s1")
        executor._strategy_states["s1"]["execution_count"] = 5
        executor.reset()
        assert executor._strategy_states["s1"]["execution_count"] == 0


class TestExecutionResult:
    def test_successful_result(self):
        r = ExecutionResult(datetime.utcnow(), [{"a": 1}], {"n1": "COMPLETED"}, True)
        assert r.success
        assert len(r.actions) == 1

    def test_failed_result(self):
        r = ExecutionResult(
            datetime.utcnow(), [], {}, False, error_message="boom"
        )
        assert not r.success
        assert r.error_message == "boom"


class TestSerializerValidate:
    def test_valid_config(self):
        config = {
            "version": "1.0",
            "nodes": [{"id": "n1", "type": "DataSourceNode", "params": {}}],
            "connections": [],
        }
        valid, errors = validate_strategy_config(config)
        assert valid
        assert errors == []

    def test_missing_version(self):
        config = {"nodes": [{"id": "n1", "type": "DataSourceNode", "params": {}}], "connections": []}
        valid, errors = validate_strategy_config(config)
        assert not valid

    def test_missing_nodes(self):
        valid, errors = validate_strategy_config({"version": "1.0", "connections": []})
        assert not valid

    def test_empty_nodes(self):
        config = {"version": "1.0", "nodes": [], "connections": []}
        valid, errors = validate_strategy_config(config)
        assert not valid

    def test_duplicate_node_ids(self):
        config = {
            "version": "1.0",
            "nodes": [
                {"id": "n1", "type": "DataSourceNode", "params": {}},
                {"id": "n1", "type": "DataSourceNode", "params": {}},
            ],
            "connections": [],
        }
        valid, errors = validate_strategy_config(config)
        assert not valid
        assert any("duplicate" in e for e in errors)

    def test_unknown_node_type(self):
        config = {
            "version": "1.0",
            "nodes": [{"id": "n1", "type": "FooBarBaz", "params": {}}],
            "connections": [],
        }
        valid, errors = validate_strategy_config(config, strict=True)
        assert not valid
        assert any("unknown node type" in e for e in errors)

    def test_connection_references_missing_node(self):
        config = {
            "version": "1.0",
            "nodes": [{"id": "n1", "type": "DataSourceNode", "params": {}}],
            "connections": [{"from": "ghost", "to": "n1"}],
        }
        valid, errors = validate_strategy_config(config)
        assert not valid

    def test_not_dict_returns_false(self):
        valid, errors = validate_strategy_config("not a dict")
        assert not valid

    def test_invalid_version_format(self):
        config = {
            "version": "abc",
            "nodes": [{"id": "n1", "type": "DataSourceNode", "params": {}}],
            "connections": [],
        }
        valid, errors = validate_strategy_config(config, strict=True)
        assert not valid

    def test_validate_profile_config_missing_strategy_nodes(self):
        valid, errors = validate_profile_config({"profile_name": "test"})
        assert not valid
        assert any("strategy_nodes" in e for e in errors)

    def test_validate_profile_config_with_valid(self):
        profile = {
            "profile_name": "Test Profile",
            "strategy_nodes": {
                "version": "1.0",
                "nodes": [{"id": "n1", "type": "DataSourceNode", "params": {}}],
                "connections": [],
            },
        }
        valid, errors = validate_profile_config(profile)
        assert valid


class TestSerializerRoundtrip:
    def test_serialize_deserialize_roundtrip(self):
        config = {
            "version": "1.0",
            "name": "My Strategy",
            "nodes": [{"id": "n1", "type": "DataSourceNode", "params": {}}],
            "connections": [],
        }
        graph = deserialize_graph("g1", config, validate=True)
        assert graph.graph_id == "g1"
        assert len(graph.get_nodes()) == 1

        serialized = serialize_graph(graph)
        assert "nodes" in serialized
        assert serialized["nodes"][0]["id"] == "n1"

    def test_deserialize_invalid_raises(self):
        with pytest.raises(ValidationError, match="validation failed"):
            deserialize_graph("g1", {"version": "1.0"}, validate=True)

    def test_deserialize_skip_validation(self):
        graph = deserialize_graph("g1", {"version": "1.0", "nodes": [], "connections": []}, validate=False)
        assert graph.graph_id == "g1"

    def test_graph_to_json_and_back(self):
        config = {
            "version": "1.0",
            "nodes": [{"id": "n1", "type": "DataSourceNode", "params": {}}],
            "connections": [],
        }
        graph = deserialize_graph("g-json", config, validate=True)
        json_str = graph_to_json(graph)
        assert isinstance(json_str, str)
        assert "n1" in json_str

        parsed = json.loads(json_str)
        assert parsed["nodes"][0]["id"] == "n1"

    def test_graph_from_json_invalid(self):
        with pytest.raises(ValidationError, match="Invalid JSON"):
            graph_from_json("g1", "not json")

    def test_migrate_config_noop(self):
        config = {"version": "1.0", "nodes": [], "connections": []}
        result = migrate_config(config, "1.0")
        assert result == config

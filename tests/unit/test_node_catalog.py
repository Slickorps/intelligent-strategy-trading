"""Unit tests for the strategy node catalog."""

from ist.strategy.graph import StrategyGraph
from ist.strategy.nodes.catalog import (
    NODE_CATALOG,
    build_node_catalog,
    default_params,
)


class TestNodeCatalog:
    def test_covers_all_graph_node_types(self) -> None:
        types = {entry["type"] for entry in build_node_catalog()}
        assert types == set(StrategyGraph.NODE_TYPE_MAP)

    def test_each_entry_has_metadata(self) -> None:
        for entry in build_node_catalog():
            assert entry["label"]
            assert entry["category"]
            assert isinstance(entry["params"], list)
            assert isinstance(entry["inputs"], list)
            assert isinstance(entry["outputs"], list)

    def test_inputs_and_outputs_derived_from_nodes(self) -> None:
        catalog = {entry["type"]: entry for entry in build_node_catalog()}
        indicator = catalog["IndicatorNode"]
        assert any(i["name"] == "price" for i in indicator["inputs"])
        assert {o["name"] for o in indicator["outputs"]} == {"value", "slope"}

    def test_catalog_metadata_matches_curated_dict(self) -> None:
        assert set(NODE_CATALOG) == set(StrategyGraph.NODE_TYPE_MAP)

    def test_default_params(self) -> None:
        params = default_params("ActionNode")
        assert params["action"] == "buy"
        assert params["size_pct"] == 0.05

    def test_default_params_are_fresh_copies(self) -> None:
        first = default_params("ThresholdNode")
        first["levels"].append(999)
        second = default_params("ThresholdNode")
        assert second["levels"] == [30, 50, 70]

    def test_data_filter_node_is_registered(self) -> None:
        assert "DataFilterNode" in StrategyGraph.NODE_TYPE_MAP

"""Strategy graph serialization, deserialization, and schema validation.

This module provides:
- JSON Schema definitions for strategy validation
- Serialization/deserialization of StrategyGraph objects
- Version migration support (e.g., v1.0 → v1.1)
"""

from typing import Any, Optional
from datetime import datetime

from ist.core.exceptions import GraphError, ValidationError
from ist.core.logging import get_logger
from ist.strategy.graph import NodeConnection, StrategyGraph

logger = get_logger(__name__)

# ============================================================
# JSON Schema Definitions
# ============================================================

STRATEGY_SCHEMA_V1 = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "https://ist.local/strategy/v1.0",
    "title": "Strategy Graph Config",
    "description": "Configuration schema for a strategy graph (version 1.0)",
    "type": "object",
    "properties": {
        "version": {
            "type": "string",
            "pattern": "^\\d+\\.\\d+$",
            "description": "Schema version for migration support"
        },
        "name": {
            "type": "string",
            "description": "Optional human-readable strategy name"
        },
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "type", "params"],
                "properties": {
                    "id": {"type": "string", "pattern": "^[a-zA-Z_][a-zA-Z0-9_]*$"},
                    "type": {
                        "type": "string",
                        "enum": [
                            "DataSourceNode", "MultiDataSourceNode",
                            "IndicatorNode",
                            "ConditionNode", "LogicGateNode", "ThresholdNode",
                            "ActionNode", "RebalanceNode", "TrailingStopNode",
                            "RiskNode", "DrawdownProtectionNode"
                        ]
                    },
                    "params": {"type": "object"},
                    "position": {
                        "type": "object",
                        "properties": {
                            "x": {"type": "number"},
                            "y": {"type": "number"}
                        }
                    }
                }
            },
            "minItems": 1
        },
        "connections": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["from", "to"],
                "properties": {
                    "from": {"type": "string"},
                    "to": {"type": "string"},
                    "from_output": {"type": "string"},
                    "to_input": {"type": "string"}
                }
            }
        }
    },
    "required": ["version", "nodes", "connections"]
}

# Schema registry for version migration
SCHEMA_REGISTRY: dict[str, dict] = {
    "1.0": STRATEGY_SCHEMA_V1,
}

# ============================================================
# Version Migration
# ============================================================

MIGRATIONS: dict[str, callable] = {
    # Future migrations:
    # "1.0": {"to": "1.1", "fn": _migrate_v1_to_v1_1},
}


def get_latest_version() -> str:
    """Get the latest supported schema version."""
    return max(SCHEMA_REGISTRY.keys(), key=lambda v: tuple(map(int, v.split("."))))


def _validate_with_schema(
    config: dict[str, Any],
    schema: Optional[dict] = None
) -> list[str]:
    """Validate configuration against JSON Schema.
    
    Uses a lightweight schema validator instead of pulling in
    the full jsonschema library as a dependency.
    
    Returns:
        List of validation error messages (empty if valid).
    """
    errors: list[str] = []
    schema = schema or STRATEGY_SCHEMA_V1

    # Check required fields
    for field in schema.get("required", []):
        if field not in config:
            errors.append(f"Missing required field: '{field}'")

    # Version check
    version = config.get("version", "")
    if version and "pattern" in schema.get("properties", {}).get("version", {}):
        import re
        pattern = schema["properties"]["version"]["pattern"]
        if not re.match(pattern, version):
            errors.append(
                f"Invalid version format '{version}', expected pattern: {pattern}"
            )

    # Validate nodes if present
    nodes = config.get("nodes", [])
    if not isinstance(nodes, list):
        errors.append("'nodes' must be an array")
    else:
        node_ids: set[str] = set()
        node_schema = (
            schema.get("properties", {})
            .get("nodes", {})
            .get("items", {})
        )
        node_props = node_schema.get("properties", {})

        for i, node in enumerate(nodes):
            if not isinstance(node, dict):
                errors.append(f"nodes[{i}]: must be an object")
                continue

            # Check required node fields
            for field in node_schema.get("required", []):
                if field not in node:
                    errors.append(f"nodes[{i}]: missing required field '{field}'")

            # Validate node id uniqueness
            node_id = node.get("id", f"<index {i}>")
            if node_id in node_ids:
                errors.append(f"nodes[{i}]: duplicate node id '{node_id}'")
            node_ids.add(node_id)

            # Validate node type
            node_type = node.get("type", "")
            allowed_types = (
                node_props.get("type", {})
                .get("enum", [])
            )
            if node_type and allowed_types and node_type not in allowed_types:
                errors.append(
                    f"nodes[{i}]: unknown node type '{node_type}'"
                )

            # Params must be a dict
            if "params" in node and not isinstance(node["params"], dict):
                errors.append(f"nodes[{i}]: 'params' must be an object")

    # Validate connections if present
    connections = config.get("connections", [])
    if not isinstance(connections, list):
        errors.append("'connections' must be an array")
    else:
        conn_schema = (
            schema.get("properties", {})
            .get("connections", {})
            .get("items", {})
        )
        for i, conn in enumerate(connections):
            if not isinstance(conn, dict):
                errors.append(f"connections[{i}]: must be an object")
                continue

            for field in conn_schema.get("required", []):
                if field not in conn:
                    errors.append(
                        f"connections[{i}]: missing required field '{field}'"
                    )

            # Validate referenced nodes exist
            from_node = conn.get("from", "")
            to_node = conn.get("to", "")
            if from_node and from_node not in node_ids:
                errors.append(
                    f"connections[{i}]: 'from' node '{from_node}' not found in nodes"
                )
            if to_node and to_node not in node_ids:
                errors.append(
                    f"connections[{i}]: 'to' node '{to_node}' not found in nodes"
                )

    return errors


def validate_strategy_config(
    config: dict[str, Any],
    strict: bool = False
) -> tuple[bool, list[str]]:
    """Validate a strategy configuration dictionary.
    
    Args:
        config: Strategy configuration to validate.
        strict: If True, validates against schema in addition to basic checks.
        
    Returns:
        (is_valid, list of error messages)
    """
    errors: list[str] = []

    # Basic structural validation
    if not isinstance(config, dict):
        return False, ["Configuration must be a dictionary"]

    if "version" not in config:
        errors.append("Missing 'version' field")

    if "nodes" not in config:
        errors.append("Missing 'nodes' field")
    elif not config["nodes"]:
        errors.append("At least one node is required")

    if "connections" not in config:
        errors.append("Missing 'connections' field")

    if errors:
        return False, errors

    # Schema validation
    schema_errors = _validate_with_schema(config)
    errors.extend(schema_errors)

    return len(errors) == 0, errors


def validate_profile_config(
    profile: dict[str, Any],
    strict: bool = False
) -> tuple[bool, list[str]]:
    """Validate a full profile configuration that wraps strategy in 'strategy_nodes'.

    Profile configs have top-level fields like profile_name, asset_allocation,
    risk_management, and a nested 'strategy_nodes' block containing the graph.

    Args:
        profile: Profile configuration dictionary (e.g. from config/examples/*.json).
        strict: If True, validates against schema in addition to basic checks.

    Returns:
        (is_valid, list of error messages)
    """
    if not isinstance(profile, dict):
        return False, ["Profile configuration must be a dictionary"]

    if "profile_name" not in profile:
        return False, ["Missing 'profile_name' field in profile"]

    strategy_config = profile.get("strategy_nodes")
    if strategy_config is None:
        return False, ["Missing 'strategy_nodes' section in profile config"]

    if not isinstance(strategy_config, dict):
        return False, ["'strategy_nodes' must be a dictionary"]

    return validate_strategy_config(strategy_config, strict=strict)


# ============================================================
# Serialization / Deserialization
# ============================================================

def serialize_graph(graph: StrategyGraph) -> dict[str, Any]:
    """Serialize a StrategyGraph to a dictionary for persistence.
    
    This is the canonical serialization method. It strips runtime
    state (execution state, errors, etc.) and only preserves
    configuration that can be used to reconstruct the graph.
    """
    config = graph.to_dict()
    
    # Strip runtime-only fields
    config.pop("is_valid", None)
    config.pop("validation_errors", None)
    config.pop("execution_order", None)

    # Strip runtime state from nodes
    for node_dict in config.get("nodes", []):
        node_dict.pop("state", None)
        node_dict.pop("inputs", None)
        node_dict.pop("outputs", None)
    
    return config


def deserialize_graph(
    graph_id: str,
    config: dict[str, Any],
    validate: bool = True,
    auto_migrate: bool = True
) -> StrategyGraph:
    """Deserialize a strategy graph from a configuration dictionary.
    
    Args:
        graph_id: Unique identifier for the graph.
        config: Configuration dictionary (from JSON file, API, etc.).
        validate: If True, validate the config before deserializing.
        auto_migrate: If True, migrate old schema versions automatically.
        
    Returns:
        Constructed StrategyGraph instance.
    """
    if validate:
        valid, errors = validate_strategy_config(config)
        if not valid:
            raise ValidationError(
                "Strategy config validation failed",
                details={"errors": errors}
            )

    # Auto-migrate if needed
    version = config.get("version", get_latest_version())
    if auto_migrate and version != get_latest_version():
        config = migrate_config(config, version)
        logger.info(
            "Strategy config auto-migrated",
            from_version=version,
            to_version=get_latest_version()
        )

    # Delegate to StrategyGraph.from_config
    graph = StrategyGraph.from_config(graph_id, config)
    
    logger.info(
        "Graph deserialized",
        graph_id=graph_id,
        node_count=len(graph.get_nodes()),
        connection_count=len(config.get("connections", []))
    )
    
    return graph


def migrate_config(
    config: dict[str, Any],
    from_version: str
) -> dict[str, Any]:
    """Migrate a strategy configuration from one version to the latest.
    
    Args:
        config: Configuration to migrate.
        from_version: Source schema version.
        
    Returns:
        Migrated configuration at the latest schema version.
    """
    current = config.copy()
    current_version = from_version

    while current_version in MIGRATIONS:
        migration = MIGRATIONS[current_version]
        logger.info(
            "Running migration",
            from_version=current_version,
            to_version=migration["to"]
        )
        current = migration["fn"](current)
        current_version = migration["to"]

    return current


# ============================================================
# Utility Functions
# ============================================================

def graph_from_json(
    graph_id: str,
    json_str: str,
    validate: bool = True
) -> StrategyGraph:
    """Create a graph from a JSON string.
    
    Args:
        graph_id: Unique identifier for the graph.
        json_str: JSON string to parse.
        validate: If True, validate before deserializing.
        
    Returns:
        Constructed StrategyGraph instance.
    """
    import json
    try:
        config = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValidationError(
            "Invalid JSON string",
            details={"error": str(e)}
        ) from e

    return deserialize_graph(graph_id, config, validate=validate)


def graph_to_json(graph: StrategyGraph, indent: int = 2) -> str:
    """Serialize a graph to a pretty-printed JSON string.
    
    Args:
        graph: Graph to serialize.
        indent: JSON indentation level.
        
    Returns:
        JSON string representation.
    """
    import json
    config = serialize_graph(graph)
    return json.dumps(config, indent=indent, default=str)


# ============================================================
# Public API
# ============================================================

__all__ = [
    "validate_strategy_config",
    "validate_profile_config",
    "serialize_graph",
    "deserialize_graph",
    "migrate_config",
    "graph_from_json",
    "graph_to_json",
    "get_latest_version",
    "STRATEGY_SCHEMA_V1",
    "SCHEMA_REGISTRY",
]
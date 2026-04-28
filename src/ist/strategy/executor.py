"""Strategy execution engine."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from ist.core.events import EventBus, EventType, Event
from ist.core.logging import get_logger
from ist.strategy.nodes.base import NodeExecutionContext
from ist.strategy.graph import StrategyGraph

logger = get_logger(__name__)


@dataclass
class ExecutionResult:
    """Result of a strategy execution cycle."""
    timestamp: datetime
    actions: list[dict[str, Any]]
    node_states: dict[str, str]
    success: bool
    error_message: Optional[str] = None


class StrategyExecutor:
    """Executes strategy graphs on market data updates.
    
    Manages the event loop for strategy execution, handling:
    - Bar/tick data updates
    - Node graph execution
    - Action generation and routing
    - Performance tracking
    """
    
    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        initial_capital: float = 100000.0
    ) -> None:
        self.event_bus = event_bus or EventBus()
        self.initial_capital = initial_capital
        
        # Strategy storage
        self._strategies: dict[str, StrategyGraph] = {}
        self._strategy_states: dict[str, dict] = {}
        
        # Execution tracking
        self._execution_history: list[ExecutionResult] = []
        self._is_running = False
        
        # Subscribe to market data events
        self.event_bus.subscribe(
            EventType.BAR_CLOSE,
            self._on_bar_close
        )
    
    def add_strategy(self, strategy_id: str, graph: StrategyGraph) -> None:
        """Add a strategy to the executor."""
        # Validate strategy
        is_valid, errors = graph.validate()
        if not is_valid:
            raise ValueError(
                f"Strategy {strategy_id} validation failed: {errors}"
            )
        
        self._strategies[strategy_id] = graph
        self._strategy_states[strategy_id] = {
            "active": False,
            "execution_count": 0,
            "last_execution": None,
            "total_actions_generated": 0,
        }
        
        logger.info(
            "Strategy added to executor",
            strategy_id=strategy_id,
            node_count=len(graph.get_nodes())
        )
    
    def remove_strategy(self, strategy_id: str) -> None:
        """Remove a strategy."""
        if strategy_id in self._strategies:
            del self._strategies[strategy_id]
            del self._strategy_states[strategy_id]
            logger.info("Strategy removed", strategy_id=strategy_id)
    
    def start_strategy(self, strategy_id: str) -> None:
        """Activate a strategy for execution."""
        if strategy_id not in self._strategy_states:
            raise ValueError(f"Strategy {strategy_id} not found")
        
        self._strategy_states[strategy_id]["active"] = True
        
        # Emit event
        self.event_bus.emit(
            self.event_bus.create_event(
                EventType.STRATEGY_STARTED,
                {"strategy_id": strategy_id},
                "executor"
            )
        )
        
        logger.info("Strategy started", strategy_id=strategy_id)
    
    def stop_strategy(self, strategy_id: str) -> None:
        """Deactivate a strategy."""
        if strategy_id in self._strategy_states:
            self._strategy_states[strategy_id]["active"] = False
            
            self.event_bus.emit(
                self.event_bus.create_event(
                    EventType.STRATEGY_STOPPED,
                    {"strategy_id": strategy_id},
                    "executor"
                )
            )
            
            logger.info("Strategy stopped", strategy_id=strategy_id)
    
    def execute_strategy(
        self,
        strategy_id: str,
        bar_data: dict[str, Any],
        portfolio_state: Optional[dict] = None
    ) -> ExecutionResult:
        """Execute a single strategy cycle.
        
        Args:
            strategy_id: ID of strategy to execute
            bar_data: Current bar/candle data
            portfolio_state: Current portfolio state
            
        Returns:
            Execution result with actions and states
        """
        if strategy_id not in self._strategies:
            return ExecutionResult(
                timestamp=datetime.utcnow(),
                actions=[],
                node_states={},
                success=False,
                error_message=f"Strategy {strategy_id} not found"
            )
        
        strategy = self._strategies[strategy_id]
        state = self._strategy_states[strategy_id]
        
        if not state["active"]:
            return ExecutionResult(
                timestamp=datetime.utcnow(),
                actions=[],
                node_states={},
                success=False,
                error_message="Strategy not active"
            )
        
        # Build execution context
        context = NodeExecutionContext(
            timestamp=datetime.utcnow(),
            bar_data=bar_data,
            portfolio_state=portfolio_state,
            custom_data={}
        )
        
        try:
            # Execute graph
            action_outputs = strategy.execute(context)
            
            # Extract actions
            actions = []
            for node_id, output in action_outputs.items():
                if output.get("action_taken"):
                    order_request = output.get("order_request", {})
                    if order_request:
                        actions.append(order_request)
            
            # Update state
            state["execution_count"] += 1
            state["last_execution"] = datetime.utcnow()
            state["total_actions_generated"] += len(actions)
            
            # Collect node states
            node_states = {
                nid: node.state.name
                for nid, node in strategy.get_nodes().items()
            }
            
            result = ExecutionResult(
                timestamp=datetime.utcnow(),
                actions=actions,
                node_states=node_states,
                success=True
            )
            
            # Emit signal event
            if actions:
                self.event_bus.emit(
                    self.event_bus.create_event(
                        EventType.SIGNAL_GENERATED,
                        {
                            "strategy_id": strategy_id,
                            "actions": actions
                        },
                        "executor"
                    )
                )
            
            return result
            
        except Exception as e:
            logger.error(
                "Strategy execution failed",
                strategy_id=strategy_id,
                error=str(e)
            )
            
            return ExecutionResult(
                timestamp=datetime.utcnow(),
                actions=[],
                node_states={},
                success=False,
                error_message=str(e)
            )
    
    def _on_bar_close(self, event: Event) -> None:
        """Handle bar close events."""
        bar_data = event.payload.get("bar_data", {})
        
        # Execute all active strategies
        for strategy_id, state in self._strategy_states.items():
            if state["active"]:
                self.execute_strategy(
                    strategy_id,
                    bar_data,
                    event.payload.get("portfolio_state")
                )
    
    def execute_all(
        self,
        bar_data: dict[str, Any],
        portfolio_state: Optional[dict] = None
    ) -> dict[str, ExecutionResult]:
        """Execute all active strategies."""
        results = {}
        
        for strategy_id in self._strategies:
            if self._strategy_states[strategy_id]["active"]:
                results[strategy_id] = self.execute_strategy(
                    strategy_id, bar_data, portfolio_state
                )
        
        return results
    
    def get_strategy_status(self, strategy_id: str) -> Optional[dict]:
        """Get strategy execution status."""
        return self._strategy_states.get(strategy_id)
    
    def get_all_status(self) -> dict[str, dict]:
        """Get all strategy statuses."""
        return self._strategy_states.copy()
    
    def reset(self) -> None:
        """Reset executor state."""
        self._execution_history.clear()
        for strategy_id in self._strategies:
            self._strategy_states[strategy_id]["execution_count"] = 0
            self._strategy_states[strategy_id]["last_execution"] = None
            self._strategy_states[strategy_id]["total_actions_generated"] = 0

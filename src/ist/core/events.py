"""Event system for inter-component communication."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable


class EventType(Enum):
    """Types of events in the system."""
    
    # Market data events
    PRICE_UPDATE = auto()
    BAR_CLOSE = auto()
    
    # Strategy events
    SIGNAL_GENERATED = auto()
    
    # Execution events
    ORDER_SUBMITTED = auto()
    ORDER_FILLED = auto()
    ORDER_REJECTED = auto()
    ORDER_CANCELLED = auto()
    
    # Portfolio events
    POSITION_OPENED = auto()
    POSITION_CLOSED = auto()
    PORTFOLIO_UPDATE = auto()
    
    # Risk events
    RISK_BREACH = auto()
    REBALANCE_TRIGGERED = auto()
    
    # System events
    STRATEGY_STARTED = auto()
    STRATEGY_STOPPED = auto()
    BACKTEST_STARTED = auto()
    BACKTEST_COMPLETED = auto()


@dataclass(frozen=True)
class Event:
    """Immutable event container."""
    
    event_type: EventType
    timestamp: datetime
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = field(default="")
    
    def __post_init__(self) -> None:
        object.__setattr__(
            self, 
            "timestamp", 
            self.timestamp if isinstance(self.timestamp, datetime) else datetime.utcnow()
        )


class EventBus:
    """Simple in-memory event bus for component communication."""
    
    def __init__(self) -> None:
        self._handlers: dict[EventType, list[Callable[[Event], None]]] = {}
    
    def subscribe(
        self, 
        event_type: EventType, 
        handler: Callable[[Event], None]
    ) -> None:
        """Subscribe a handler to an event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
    
    def unsubscribe(
        self, 
        event_type: EventType, 
        handler: Callable[[Event], None]
    ) -> None:
        """Unsubscribe a handler from an event type."""
        if event_type in self._handlers:
            self._handlers[event_type] = [
                h for h in self._handlers[event_type] if h != handler
            ]
    
    def emit(self, event: Event) -> None:
        """Emit an event to all subscribed handlers."""
        handlers = self._handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                # Log error but don't stop other handlers
                print(f"Event handler error: {e}")
    
    def create_event(
        self,
        event_type: EventType,
        payload: dict[str, Any],
        source: str = ""
    ) -> Event:
        """Factory method to create events."""
        return Event(
            event_type=event_type,
            timestamp=datetime.utcnow(),
            payload=payload,
            source=source
        )

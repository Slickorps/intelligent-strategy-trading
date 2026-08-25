"""Order Management System (OMS).

Tracks order lifecycle from creation to completion.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Optional
from uuid import uuid4

from ist.core.logging import get_logger
from ist.execution.adapter import (
    Order,
    OrderResult,
    OrderStatus,
    BrokerAdapter,
)

logger = get_logger(__name__)


class OrderState(Enum):
    """Extended order states for OMS tracking."""
    CREATED = auto()
    VALIDATED = auto()
    SUBMITTED = auto()
    ACKNOWLEDGED = auto()
    PENDING = auto()
    PARTIAL_FILL = auto()
    FILLED = auto()
    CANCEL_REQUESTED = auto()
    CANCELLED = auto()
    REJECTED = auto()
    EXPIRED = auto()
    ERROR = auto()


@dataclass
class OrderEvent:
    """Order lifecycle event."""
    timestamp: datetime
    state: OrderState
    description: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ManagedOrder:
    """Order with full lifecycle tracking."""
    
    internal_id: str
    client_order_id: str
    order: Order
    
    # Lifecycle
    state: OrderState = OrderState.CREATED
    events: list[OrderEvent] = field(default_factory=list)
    
    # Broker info
    broker_id: Optional[str] = None
    broker_order_id: Optional[str] = None
    
    # Results
    result: Optional[OrderResult] = None
    
    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    submitted_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    def add_event(self, state: OrderState, description: str, **data) -> None:
        """Add lifecycle event."""
        event = OrderEvent(
            timestamp=datetime.utcnow(),
            state=state,
            description=description,
            data=data
        )
        self.events.append(event)
        self.state = state


class OrderManagementSystem:
    """Order Management System.
    
    Manages order lifecycle:
    1. Order creation and validation
    2. Order submission to broker
    3. Order tracking and updates
    4. Fill processing
    5. Order history
    
    Usage:
        oms = OrderManagementSystem(broker_adapter)
        
        # Create order
        order_id = oms.create_order(
            symbol="EURUSD",
            side=OrderSide.BUY,
            quantity=10000
        )
        
        # Submit
        await oms.submit_order(order_id)
        
        # Check status
        status = oms.get_order_status(order_id)
    """
    
    def __init__(self, broker: BrokerAdapter) -> None:
        self.broker = broker
        
        # Order storage
        self._orders: dict[str, ManagedOrder] = {}
        self._broker_to_internal: dict[str, str] = {}
        
        # Statistics
        self._stats = {
            "total_created": 0,
            "total_submitted": 0,
            "total_filled": 0,
            "total_cancelled": 0,
            "total_rejected": 0,
        }
    
    def create_order(
        self,
        symbol: str,
        side: Any,  # OrderSide
        quantity: float,
        order_type: Any = None,  # OrderType
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        time_in_force: Any = None,
        **kwargs
    ) -> str:
        """Create new order."""
        # Generate IDs
        internal_id = str(uuid4())
        client_id = f"cl_{internal_id[:8]}"
        
        # Create order
        order = Order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type or OrderType.MARKET,
            limit_price=limit_price,
            stop_price=stop_price,
            time_in_force=time_in_force or TimeInForce.GTC,
            client_order_id=client_id
        )
        
        # Create managed order
        managed = ManagedOrder(
            internal_id=internal_id,
            client_order_id=client_id,
            order=order
        )
        
        managed.add_event(
            OrderState.CREATED,
            f"Order created: {symbol} {side.name} {quantity}"
        )
        
        # Validate
        validation = self._validate_order(order)
        if validation["valid"]:
            managed.add_event(
                OrderState.VALIDATED,
                "Order validated successfully"
            )
        else:
            managed.add_event(
                OrderState.ERROR,
                f"Validation failed: {validation['error']}"
            )
            raise ValueError(validation["error"])
        
        self._orders[internal_id] = managed
        self._stats["total_created"] += 1
        
        logger.info(
            "Order created",
            internal_id=internal_id,
            symbol=symbol,
            side=side.name
        )
        
        return internal_id
    
    async def submit_order(self, internal_id: str) -> OrderResult:
        """Submit order to broker."""
        managed = self._get_order(internal_id)
        
        if managed.state not in (OrderState.CREATED, OrderState.VALIDATED):
            raise ValueError(f"Cannot submit order in state: {managed.state}")
        
        managed.submitted_at = datetime.utcnow()
        managed.add_event(
            OrderState.SUBMITTED,
            "Order submitted to broker"
        )
        
        try:
            # Submit to broker
            result = await self.broker.place_order(managed.order)
            
            # Update with broker response
            managed.result = result
            managed.broker_order_id = result.order_id
            self._broker_to_internal[result.order_id] = internal_id
            
            managed.add_event(
                OrderState.ACKNOWLEDGED,
                f"Order acknowledged by broker: {result.order_id}",
                broker_order_id=result.order_id
            )
            
            # Process result
            if result.status == OrderStatus.FILLED:
                await self._process_fill(internal_id, result)
            elif result.status == OrderStatus.REJECTED:
                await self._process_rejection(internal_id, result)
            elif result.status == OrderStatus.PENDING:
                managed.add_event(
                    OrderState.PENDING,
                    "Order pending execution"
                )
            
            self._stats["total_submitted"] += 1
            
            return result
            
        except Exception as e:
            managed.add_event(
                OrderState.ERROR,
                f"Submission failed: {str(e)}"
            )
            logger.error(
                "Order submission failed",
                internal_id=internal_id,
                error=str(e)
            )
            raise
    
    async def cancel_order(self, internal_id: str) -> bool:
        """Request order cancellation."""
        managed = self._get_order(internal_id)
        
        if managed.state in (OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED):
            return False
        
        managed.add_event(
            OrderState.CANCEL_REQUESTED,
            "Cancellation requested"
        )
        
        if managed.broker_order_id:
            success = await self.broker.cancel_order(managed.broker_order_id)
            
            if success:
                managed.add_event(
                    OrderState.CANCELLED,
                    "Order cancelled"
                )
                managed.completed_at = datetime.utcnow()
                self._stats["total_cancelled"] += 1
            
            return success
        
        return False
    
    async def update_order_status(self, internal_id: str) -> Optional[OrderResult]:
        """Poll broker for order status update."""
        managed = self._get_order(internal_id)
        
        if not managed.broker_order_id:
            return None
        
        result = await self.broker.get_order_status(managed.broker_order_id)
        
        if result and result != managed.result:
            managed.result = result
            
            # Process state change
            if result.status == OrderStatus.FILLED:
                await self._process_fill(internal_id, result)
            elif result.status == OrderStatus.PARTIAL_FILL:
                managed.add_event(
                    OrderState.PARTIAL_FILL,
                    f"Partial fill: {result.filled_quantity}/{managed.order.quantity}"
                )
            elif result.status == OrderStatus.CANCELLED:
                managed.add_event(
                    OrderState.CANCELLED,
                    "Order cancelled"
                )
            elif result.status == OrderStatus.EXPIRED:
                managed.add_event(
                    OrderState.EXPIRED,
                    "Order expired"
                )
                managed.completed_at = datetime.utcnow()
        
        return result
    
    def get_order(self, internal_id: str) -> Optional[ManagedOrder]:
        """Get order by internal ID."""
        return self._orders.get(internal_id)
    
    def get_order_by_broker_id(self, broker_id: str) -> Optional[ManagedOrder]:
        """Get order by broker ID."""
        internal_id = self._broker_to_internal.get(broker_id)
        if internal_id:
            return self._orders.get(internal_id)
        return None
    
    def list_orders(
        self,
        state: Optional[OrderState] = None,
        symbol: Optional[str] = None
    ) -> list[ManagedOrder]:
        """List orders with optional filtering."""
        orders = list(self._orders.values())
        
        if state:
            orders = [o for o in orders if o.state == state]
        
        if symbol:
            orders = [o for o in orders if o.order.symbol == symbol]
        
        return orders
    
    def get_open_orders(self) -> list[ManagedOrder]:
        """Get all open (active) orders."""
        return self.list_orders(
            state=OrderState.SUBMITTED
        ) + self.list_orders(
            state=OrderState.PARTIAL_FILL
        )
    
    def get_order_history(self, internal_id: str) -> list[OrderEvent]:
        """Get order lifecycle history."""
        managed = self._get_order(internal_id)
        return managed.events.copy()
    
    def get_statistics(self) -> dict[str, int]:
        """Get OMS statistics."""
        return self._stats.copy()
    
    def _get_order(self, internal_id: str) -> ManagedOrder:
        """Get order or raise error."""
        if internal_id not in self._orders:
            raise ValueError(f"Order not found: {internal_id}")
        return self._orders[internal_id]
    
    def _validate_order(self, order: Order) -> dict[str, Any]:
        """Validate order parameters."""
        if order.quantity <= 0:
            return {"valid": False, "error": "Quantity must be positive"}
        
        if not order.symbol:
            return {"valid": False, "error": "Symbol is required"}
        
        if order.order_type == OrderType.LIMIT and order.limit_price is None:
            return {"valid": False, "error": "Limit price required for limit orders"}
        
        if order.order_type == OrderType.STOP and order.stop_price is None:
            return {"valid": False, "error": "Stop price required for stop orders"}
        
        return {"valid": True, "error": None}
    
    async def _process_fill(
        self,
        internal_id: str,
        result: OrderResult
    ) -> None:
        """Process order fill."""
        managed = self._get_order(internal_id)
        
        managed.add_event(
            OrderState.FILLED,
            f"Order filled: {result.filled_quantity} @ {result.avg_fill_price}",
            fill_price=result.avg_fill_price,
            commission=result.commission
        )
        
        managed.completed_at = datetime.utcnow()
        self._stats["total_filled"] += 1
        
        logger.info(
            "Order filled",
            internal_id=internal_id,
            symbol=managed.order.symbol,
            price=result.avg_fill_price
        )
    
    async def _process_rejection(
        self,
        internal_id: str,
        result: OrderResult
    ) -> None:
        """Process order rejection."""
        managed = self._get_order(internal_id)
        
        managed.add_event(
            OrderState.REJECTED,
            f"Order rejected: {result.error_message}",
            error=result.error_message
        )
        
        managed.completed_at = datetime.utcnow()
        self._stats["total_rejected"] += 1
        
        logger.warning(
            "Order rejected",
            internal_id=internal_id,
            error=result.error_message
        )


# Import needed for type hints
from ist.execution.adapter import OrderType, TimeInForce

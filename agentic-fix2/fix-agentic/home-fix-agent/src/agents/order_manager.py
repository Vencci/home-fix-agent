"""Order Manager: handle confirmation and (mock) order placement."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from src.models.schemas import OrderRecord, OrderStatus, ProductResult


def create_order(session_id: str, product: ProductResult, quantity: int = 1) -> OrderRecord:
    """Create a pending order record for user confirmation."""
    return OrderRecord(
        session_id=session_id,
        result_id=product.result_id,
        product_title=product.title,
        quantity=quantity,
        unit_price_cents=product.price_cents,
        total_price_cents=product.price_cents * quantity,
        shipping_cost_cents=0,
        status=OrderStatus.PENDING,
    )


def confirm_order(order: OrderRecord) -> OrderRecord:
    """Mark order as confirmed and place it (mock placement)."""
    order.status = OrderStatus.PLACED
    order.confirmed_at = datetime.now(timezone.utc)
    order.placed_at = datetime.now(timezone.utc)
    order.retailer_order_id = f"MOCK-{uuid.uuid4().hex[:8].upper()}"
    return order


def cancel_order(order: OrderRecord) -> OrderRecord:
    """Mark order as cancelled."""
    order.status = OrderStatus.CANCELLED
    return order

"""Read-only view of the caller's Action Center queue for API clients.

In Semi-Auto mode placeorder and the other order calls are queued in the Action Center and
answer with a pending_order_id only. This service lets the API client that queued an order
see what became of it (pending, approved or rejected, and after approval the broker order id
and broker status) without the browser session the Action Center page needs. It never
changes an order: approving and rejecting stay in the Action Center, with the trader.
"""

import json
from typing import Any

from database.action_center_db import get_pending_orders
from database.auth_db import verify_api_key
from utils.logging import get_logger

logger = get_logger(__name__)

# Never returned, even if a client sent them inside an order.
_SECRET_KEYS = {"apikey", "api_key"}


def _order_fields(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if k not in _SECRET_KEYS}


def _serialise(pending_order) -> dict[str, Any]:
    return {
        "pending_order_id": pending_order.id,
        "api_type": pending_order.api_type,
        "status": pending_order.status,
        "created_at_ist": pending_order.created_at_ist,
        "approved_at_ist": pending_order.approved_at_ist,
        "rejected_at_ist": pending_order.rejected_at_ist,
        "rejected_reason": pending_order.rejected_reason,
        "broker_order_id": pending_order.broker_order_id,
        "broker_status": pending_order.broker_status,
        "order": _order_fields(pending_order.order_data),
    }


def get_pending_orders_for_api(
    api_key: str, status: str | None = None, limit: int = 100
) -> tuple[bool, dict[str, Any], int]:
    """The caller's pending orders, newest first.

    Args:
        api_key: OpenAlgo API key; only that user's orders are returned
        status: Optional filter: 'pending', 'approved' or 'rejected'
        limit: Maximum number of orders returned

    Returns:
        Tuple of (success, response data, HTTP status code)
    """
    user_id = verify_api_key(api_key)
    if not user_id:
        return False, {"status": "error", "message": "Invalid openalgo apikey"}, 403
    try:
        orders = get_pending_orders(user_id, status=status)[:limit]
        data = {"orders": [_serialise(order) for order in orders]}
        return True, {"status": "success", "data": data}, 200
    except Exception as e:
        logger.exception(f"Error reading pending orders for the API: {e}")
        return False, {"status": "error", "message": "Could not read the Action Center"}, 500

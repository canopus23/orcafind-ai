import time
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class SubscriptionGrant:
    user_id: str
    plan: str  # "pro"
    created_at: float = field(default_factory=lambda: time.time())
    source: str = "razorpay"
    order_id: Optional[str] = None
    payment_id: Optional[str] = None


_USER_GRANTS: Dict[str, SubscriptionGrant] = {}
_ORDER_TO_USER: Dict[str, str] = {}
_IMAGE_USAGE: Dict[str, int] = {}


def get_image_usage(user_id: str) -> int:
    return int(_IMAGE_USAGE.get(user_id, 0))


def record_image_usage(user_id: str, n: int = 1) -> int:
    """
    Increment and return the new usage count.
    This is an in-memory counter for MVP purposes.
    """
    inc = max(1, int(n or 1))
    _IMAGE_USAGE[user_id] = get_image_usage(user_id) + inc
    return _IMAGE_USAGE[user_id]


def link_order_to_user(order_id: str, user_id: str):
    _ORDER_TO_USER[order_id] = user_id


def get_user_for_order(order_id: str) -> Optional[str]:
    return _ORDER_TO_USER.get(order_id)


def grant_pro(*, user_id: str, order_id: str, payment_id: str):
    _USER_GRANTS[user_id] = SubscriptionGrant(
        user_id=user_id,
        plan="pro",
        source="razorpay",
        order_id=order_id,
        payment_id=payment_id,
    )


def is_pro(user_id: str) -> bool:
    grant = _USER_GRANTS.get(user_id)
    return bool(grant and grant.plan == "pro")

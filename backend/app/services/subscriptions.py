import os
import time
from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.db import get_engine


def _engine() -> Optional[Engine]:
    try:
        return get_engine()
    except Exception:
        # Allow local/dev boot without DB if desired.
        if os.getenv("ENV", "").strip().lower() in {"prod", "production"}:
            raise
        return None


def init_schema() -> None:
    """
    Create required tables if missing.
    In production, prefer migrations, but this keeps Railway deploys safe.
    """
    engine = _engine()
    if not engine:
        return

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS subscriptions (
                  user_id TEXT PRIMARY KEY,
                  plan TEXT NOT NULL,
                  source TEXT NOT NULL,
                  order_id TEXT,
                  payment_id TEXT,
                  created_at BIGINT NOT NULL
                );
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS order_links (
                  order_id TEXT PRIMARY KEY,
                  user_id TEXT NOT NULL
                );
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS usage_counters (
                  user_id TEXT PRIMARY KEY,
                  image_used INTEGER NOT NULL DEFAULT 0,
                  updated_at BIGINT NOT NULL
                );
                """
            )
        )


def link_order_to_user(order_id: str, user_id: str):
    engine = _engine()
    if not engine:
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO order_links (order_id, user_id)
                VALUES (:order_id, :user_id)
                ON CONFLICT (order_id) DO UPDATE SET user_id = EXCLUDED.user_id;
                """
            ),
            {"order_id": order_id, "user_id": user_id},
        )


def get_user_for_order(order_id: str) -> Optional[str]:
    engine = _engine()
    if not engine:
        return None
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT user_id FROM order_links WHERE order_id = :order_id"),
            {"order_id": order_id},
        ).fetchone()
        return str(row[0]) if row else None


def grant_pro(*, user_id: str, order_id: str, payment_id: str):
    engine = _engine()
    if not engine:
        return
    created_at = int(time.time())
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO subscriptions (user_id, plan, source, order_id, payment_id, created_at)
                VALUES (:user_id, 'pro', 'razorpay', :order_id, :payment_id, :created_at)
                ON CONFLICT (user_id) DO UPDATE SET
                  plan = EXCLUDED.plan,
                  source = EXCLUDED.source,
                  order_id = EXCLUDED.order_id,
                  payment_id = EXCLUDED.payment_id,
                  created_at = EXCLUDED.created_at;
                """
            ),
            {
                "user_id": user_id,
                "order_id": order_id,
                "payment_id": payment_id,
                "created_at": created_at,
            },
        )


def is_pro(user_id: str) -> bool:
    engine = _engine()
    if not engine:
        return False
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT plan FROM subscriptions WHERE user_id = :user_id"),
            {"user_id": user_id},
        ).fetchone()
        return bool(row and str(row[0]).lower() == "pro")


def get_image_usage(user_id: str) -> int:
    engine = _engine()
    if not engine:
        return 0
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT image_used FROM usage_counters WHERE user_id = :user_id"),
            {"user_id": user_id},
        ).fetchone()
        return int(row[0]) if row else 0


def record_image_usage(user_id: str, n: int = 1) -> int:
    engine = _engine()
    if not engine:
        return 0
    inc = max(1, int(n or 1))
    now = int(time.time())
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                INSERT INTO usage_counters (user_id, image_used, updated_at)
                VALUES (:user_id, :inc, :now)
                ON CONFLICT (user_id) DO UPDATE SET
                  image_used = usage_counters.image_used + :inc,
                  updated_at = :now
                RETURNING image_used;
                """
            ),
            {"user_id": user_id, "inc": inc, "now": now},
        ).fetchone()
        return int(row[0]) if row else get_image_usage(user_id)


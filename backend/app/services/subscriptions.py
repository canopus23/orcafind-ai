import os
import time
import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.db import get_engine

logger = logging.getLogger("orcafind.subscriptions")

_USAGE_FIELDS = {"text_used", "vision_used", "builder_used", "image_used"}


def is_usage_db_configured() -> bool:
    return bool((os.getenv("DATABASE_URL") or "").strip())


def _engine() -> Optional[Engine]:
    # Never crash the whole service on DB trouble; callers can decide how to fail.
    if not is_usage_db_configured():
        return None
    try:
        return get_engine()
    except Exception:
        return None


def init_schema() -> None:
    """
    Create required tables if missing.
    In production, prefer migrations, but this keeps Railway deploys safe.
    """
    engine = _engine()
    if not engine:
        return

    try:
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
                      period_key INTEGER NOT NULL DEFAULT 0,
                      text_used INTEGER NOT NULL DEFAULT 0,
                      vision_used INTEGER NOT NULL DEFAULT 0,
                      builder_used INTEGER NOT NULL DEFAULT 0,
                      image_used INTEGER NOT NULL DEFAULT 0,
                      updated_at BIGINT NOT NULL
                    );
                    """
                )
            )

            # Backward-compatible column adds (for older deployments).
            conn.execute(text("ALTER TABLE usage_counters ADD COLUMN IF NOT EXISTS period_key INTEGER NOT NULL DEFAULT 0;"))
            conn.execute(text("ALTER TABLE usage_counters ADD COLUMN IF NOT EXISTS text_used INTEGER NOT NULL DEFAULT 0;"))
            conn.execute(text("ALTER TABLE usage_counters ADD COLUMN IF NOT EXISTS vision_used INTEGER NOT NULL DEFAULT 0;"))
            conn.execute(text("ALTER TABLE usage_counters ADD COLUMN IF NOT EXISTS builder_used INTEGER NOT NULL DEFAULT 0;"))
            conn.execute(text("ALTER TABLE usage_counters ADD COLUMN IF NOT EXISTS image_used INTEGER NOT NULL DEFAULT 0;"))
    except Exception:
        logger.exception("init_schema failed (DB unreachable). Continuing without schema init.")
        return


def _period_key(now: Optional[int] = None) -> int:
    ts = int(now or time.time())
    # Use UTC so billing/usage periods are stable regardless of server locale.
    return int(time.strftime("%Y%m", time.gmtime(ts)))


def _ensure_usage_row(conn, *, user_id: str, period_key: int, now: int) -> None:
    row = conn.execute(
        text("SELECT period_key FROM usage_counters WHERE user_id = :user_id"),
        {"user_id": user_id},
    ).fetchone()

    if not row:
        conn.execute(
            text(
                """
                INSERT INTO usage_counters (user_id, period_key, text_used, vision_used, builder_used, image_used, updated_at)
                VALUES (:user_id, :period_key, 0, 0, 0, 0, :now)
                ON CONFLICT (user_id) DO NOTHING;
                """
            ),
            {"user_id": user_id, "period_key": period_key, "now": now},
        )
        return

    stored_period = int(row[0] or 0)
    if stored_period != period_key:
        conn.execute(
            text(
                """
                UPDATE usage_counters
                SET period_key = :period_key,
                    text_used = 0,
                    vision_used = 0,
                    builder_used = 0,
                    image_used = 0,
                    updated_at = :now
                WHERE user_id = :user_id;
                """
            ),
            {"user_id": user_id, "period_key": period_key, "now": now},
        )


def get_usage(user_id: str) -> dict:
    """
    Returns the current monthly usage counters for the user.
    If the stored period differs from the current UTC month, counters reset automatically.
    """
    engine = _engine()
    if not engine:
        return {"period_key": _period_key(), "text_used": 0, "vision_used": 0, "builder_used": 0, "image_used": 0}

    now = int(time.time())
    period = _period_key(now)
    try:
        with engine.begin() as conn:
            _ensure_usage_row(conn, user_id=user_id, period_key=period, now=now)
            row = conn.execute(
                text(
                    """
                    SELECT period_key, text_used, vision_used, builder_used, image_used
                    FROM usage_counters
                    WHERE user_id = :user_id
                    """
                ),
                {"user_id": user_id},
            ).fetchone()
            if not row:
                return {"period_key": period, "text_used": 0, "vision_used": 0, "builder_used": 0, "image_used": 0}
            return {
                "period_key": int(row[0] or period),
                "text_used": int(row[1] or 0),
                "vision_used": int(row[2] or 0),
                "builder_used": int(row[3] or 0),
                "image_used": int(row[4] or 0),
            }
    except Exception:
        logger.exception("get_usage failed")
        return {"period_key": period, "text_used": 0, "vision_used": 0, "builder_used": 0, "image_used": 0}


def record_usage(user_id: str, field: str, n: int = 1) -> int:
    """
    Increments a specific monthly counter and returns the new value.
    Field must be one of: text_used, vision_used, builder_used, image_used.
    """
    if field not in _USAGE_FIELDS:
        raise ValueError("Unsupported usage field")

    engine = _engine()
    if not engine:
        return 0

    inc = max(1, int(n or 1))
    now = int(time.time())
    period = _period_key(now)

    try:
        with engine.begin() as conn:
            _ensure_usage_row(conn, user_id=user_id, period_key=period, now=now)
            row = conn.execute(
                text(
                    f"""
                    UPDATE usage_counters
                    SET {field} = {field} + :inc,
                        updated_at = :now
                    WHERE user_id = :user_id
                    RETURNING {field};
                    """
                ),
                {"user_id": user_id, "inc": inc, "now": now},
            ).fetchone()
            return int(row[0]) if row else 0
    except Exception:
        logger.exception("record_usage failed")
        return int(get_usage(user_id).get(field, 0))


def link_order_to_user(order_id: str, user_id: str):
    engine = _engine()
    if not engine:
        return
    try:
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
    except Exception:
        logger.exception("link_order_to_user failed")


def get_user_for_order(order_id: str) -> Optional[str]:
    engine = _engine()
    if not engine:
        return None
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text("SELECT user_id FROM order_links WHERE order_id = :order_id"),
                {"order_id": order_id},
            ).fetchone()
            return str(row[0]) if row else None
    except Exception:
        logger.exception("get_user_for_order failed")
        return None


def grant_pro(*, user_id: str, order_id: str, payment_id: str):
    engine = _engine()
    if not engine:
        return
    created_at = int(time.time())
    try:
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
    except Exception:
        logger.exception("grant_pro failed")


def is_pro(user_id: str) -> bool:
    engine = _engine()
    if not engine:
        return False
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text("SELECT plan FROM subscriptions WHERE user_id = :user_id"),
                {"user_id": user_id},
            ).fetchone()
            return bool(row and str(row[0]).lower() == "pro")
    except Exception:
        logger.exception("is_pro failed")
        return False


def get_image_usage(user_id: str) -> int:
    return int(get_usage(user_id).get("image_used", 0))


def record_image_usage(user_id: str, n: int = 1) -> int:
    return record_usage(user_id, "image_used", n=n)

import logging
import os
import time

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.db import get_engine

logger = logging.getLogger("orcafind.subscriptions")

_USAGE_FIELDS = {"text_used", "vision_used", "builder_used", "image_used"}
_PLANS = {"free", "starter", "pro", "business"}


def is_usage_db_configured() -> bool:
    return bool((os.getenv("DATABASE_URL") or "").strip())


def _engine() -> Engine | None:
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
            # Legacy table kept for backward compatibility (older "order-based" upgrades).
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
                text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS created_at BIGINT;")
            )
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS order_links (
                      order_id TEXT PRIMARY KEY,
                      user_id TEXT NOT NULL,
                      plan TEXT
                    );
                    """
                )
            )
            conn.execute(text("ALTER TABLE order_links ADD COLUMN IF NOT EXISTS plan TEXT;"))

            # New subscription state table (production-grade SaaS semantics).
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS subscription_state (
                      user_id TEXT PRIMARY KEY,
                      provider TEXT NOT NULL DEFAULT 'razorpay',
                      subscription_id TEXT,
                      customer_id TEXT,
                      plan TEXT NOT NULL,
                      status TEXT NOT NULL,
                      current_period_start BIGINT,
                      current_period_end BIGINT,
                      cancel_at_cycle_end INTEGER NOT NULL DEFAULT 0,
                      scheduled_plan TEXT,
                      updated_at BIGINT NOT NULL,
                      created_at BIGINT NOT NULL
                    );
                    """
                )
            )
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_subscription_state_subscription_id "
                    "ON subscription_state(subscription_id);"
                )
            )

            # Webhook idempotency table (dedupe by digest of the raw request body).
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS webhook_events (
                      digest TEXT PRIMARY KEY,
                      provider TEXT NOT NULL DEFAULT 'razorpay',
                      received_at BIGINT NOT NULL
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
            conn.execute(
                text(
                    "ALTER TABLE usage_counters "
                    "ADD COLUMN IF NOT EXISTS period_key INTEGER NOT NULL DEFAULT 0;"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE usage_counters "
                    "ADD COLUMN IF NOT EXISTS text_used INTEGER NOT NULL DEFAULT 0;"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE usage_counters "
                    "ADD COLUMN IF NOT EXISTS vision_used INTEGER NOT NULL DEFAULT 0;"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE usage_counters "
                    "ADD COLUMN IF NOT EXISTS builder_used INTEGER NOT NULL DEFAULT 0;"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE usage_counters "
                    "ADD COLUMN IF NOT EXISTS image_used INTEGER NOT NULL DEFAULT 0;"
                )
            )
    except Exception:
        logger.exception("init_schema failed (DB unreachable). Continuing without schema init.")
        return


def _normalize_plan(plan: str | None) -> str:
    p = (plan or "").strip().lower()
    return p if p in _PLANS else ""


def record_webhook_digest(*, digest: str, provider: str = "razorpay") -> bool:
    """
    Returns True if the digest was inserted (new event), False if it already existed.
    """
    engine = _engine()
    if not engine:
        return True
    now = int(time.time())
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO webhook_events (digest, provider, received_at)
                    VALUES (:digest, :provider, :received_at)
                    ON CONFLICT (digest) DO NOTHING;
                    """
                ),
                {"digest": digest, "provider": provider, "received_at": now},
            )
            row = conn.execute(
                text("SELECT received_at FROM webhook_events WHERE digest = :digest"),
                {"digest": digest},
            ).fetchone()
            return bool(row and int(row[0] or 0) == now)
    except Exception:
        logger.exception("record_webhook_digest failed")
        return True


def upsert_subscription_state(
    *,
    user_id: str,
    provider: str = "razorpay",
    subscription_id: str | None,
    customer_id: str | None,
    plan: str,
    status: str,
    current_period_start: int | None,
    current_period_end: int | None,
    cancel_at_cycle_end: bool,
    scheduled_plan: str | None,
):
    engine = _engine()
    if not engine:
        return
    now = int(time.time())
    plan_norm = _normalize_plan(plan) or "free"
    sched_norm = _normalize_plan(scheduled_plan) or None
    provider_norm = (provider or "razorpay").strip().lower() or "razorpay"
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO subscription_state (
                      user_id,
                      provider,
                      subscription_id,
                      customer_id,
                      plan,
                      status,
                      current_period_start,
                      current_period_end,
                      cancel_at_cycle_end,
                      scheduled_plan,
                      updated_at,
                      created_at
                    )
                    VALUES (
                      :user_id,
                      :provider,
                      :subscription_id,
                      :customer_id,
                      :plan,
                      :status,
                      :current_period_start,
                      :current_period_end,
                      :cancel_at_cycle_end,
                      :scheduled_plan,
                      :updated_at,
                      :created_at
                    )
                    ON CONFLICT (user_id) DO UPDATE SET
                      provider = EXCLUDED.provider,
                      subscription_id = COALESCE(
                        EXCLUDED.subscription_id,
                        subscription_state.subscription_id
                      ),
                      customer_id = COALESCE(
                        EXCLUDED.customer_id,
                        subscription_state.customer_id
                      ),
                      plan = EXCLUDED.plan,
                      status = EXCLUDED.status,
                      current_period_start = COALESCE(
                        EXCLUDED.current_period_start,
                        subscription_state.current_period_start
                      ),
                      current_period_end = COALESCE(
                        EXCLUDED.current_period_end,
                        subscription_state.current_period_end
                      ),
                      cancel_at_cycle_end = EXCLUDED.cancel_at_cycle_end,
                      scheduled_plan = EXCLUDED.scheduled_plan,
                      updated_at = EXCLUDED.updated_at;
                    """
                ),
                {
                    "user_id": user_id,
                    "provider": provider_norm,
                    "subscription_id": subscription_id,
                    "customer_id": customer_id,
                    "plan": plan_norm,
                    "status": (status or "").strip().lower() or "unknown",
                    "current_period_start": (
                        int(current_period_start) if current_period_start else None
                    ),
                    "current_period_end": int(current_period_end) if current_period_end else None,
                    "cancel_at_cycle_end": 1 if cancel_at_cycle_end else 0,
                    "scheduled_plan": sched_norm,
                    "updated_at": now,
                    "created_at": now,
                },
            )
    except Exception:
        logger.exception("upsert_subscription_state failed")


def get_subscription_state(user_id: str) -> dict | None:
    engine = _engine()
    if not engine:
        return None
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT provider, subscription_id, customer_id, plan, status,
                           current_period_start, current_period_end,
                           cancel_at_cycle_end, scheduled_plan, updated_at, created_at
                    FROM subscription_state
                    WHERE user_id = :user_id
                    """
                ),
                {"user_id": user_id},
            ).fetchone()
            if not row:
                return None
            return {
                "provider": row[0],
                "subscription_id": row[1],
                "customer_id": row[2],
                "plan": row[3],
                "status": row[4],
                "current_period_start": row[5],
                "current_period_end": row[6],
                "cancel_at_cycle_end": bool(int(row[7] or 0)),
                "scheduled_plan": row[8],
                "updated_at": row[9],
                "created_at": row[10],
            }
    except Exception:
        logger.exception("get_subscription_state failed")
        return None


def get_user_for_subscription(subscription_id: str) -> str | None:
    engine = _engine()
    if not engine:
        return None
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text(
                    "SELECT user_id FROM subscription_state "
                    "WHERE subscription_id = :subscription_id"
                ),
                {"subscription_id": subscription_id},
            ).fetchone()
            return str(row[0]) if row else None
    except Exception:
        logger.exception("get_user_for_subscription failed")
        return None


def set_scheduled_plan(*, user_id: str, scheduled_plan: str | None):
    engine = _engine()
    if not engine:
        return
    now = int(time.time())
    sched_norm = _normalize_plan(scheduled_plan) or None
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE subscription_state
                    SET scheduled_plan = :scheduled_plan,
                        updated_at = :updated_at
                    WHERE user_id = :user_id;
                    """
                ),
                {"scheduled_plan": sched_norm, "updated_at": now, "user_id": user_id},
            )
    except Exception:
        logger.exception("set_scheduled_plan failed")


def _period_key(now: int | None = None) -> int:
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
                INSERT INTO usage_counters (
                  user_id,
                  period_key,
                  text_used,
                  vision_used,
                  builder_used,
                  image_used,
                  updated_at
                )
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
        return {
            "period_key": _period_key(),
            "text_used": 0,
            "vision_used": 0,
            "builder_used": 0,
            "image_used": 0,
        }

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
                return {
                    "period_key": period,
                    "text_used": 0,
                    "vision_used": 0,
                    "builder_used": 0,
                    "image_used": 0,
                }
            return {
                "period_key": int(row[0] or period),
                "text_used": int(row[1] or 0),
                "vision_used": int(row[2] or 0),
                "builder_used": int(row[3] or 0),
                "image_used": int(row[4] or 0),
            }
    except Exception:
        logger.exception("get_usage failed")
        return {
            "period_key": period,
            "text_used": 0,
            "vision_used": 0,
            "builder_used": 0,
            "image_used": 0,
        }


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


def link_order_to_user(order_id: str, user_id: str, *, plan: str | None = None):
    engine = _engine()
    if not engine:
        return
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO order_links (order_id, user_id, plan)
                    VALUES (:order_id, :user_id, :plan)
                    ON CONFLICT (order_id) DO UPDATE SET
                      user_id = EXCLUDED.user_id,
                      plan = COALESCE(EXCLUDED.plan, order_links.plan);
                    """
                ),
                {"order_id": order_id, "user_id": user_id, "plan": (plan or None)},
            )
    except Exception:
        logger.exception("link_order_to_user failed")


def get_user_for_order(order_id: str) -> str | None:
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


def get_plan_for_order(order_id: str) -> str | None:
    engine = _engine()
    if not engine:
        return None
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text("SELECT plan FROM order_links WHERE order_id = :order_id"),
                {"order_id": order_id},
            ).fetchone()
            plan = str(row[0]).strip().lower() if row and row[0] else ""
            return plan or None
    except Exception:
        logger.exception("get_plan_for_order failed")
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
                    INSERT INTO subscriptions (
                      user_id,
                      plan,
                      source,
                      order_id,
                      payment_id,
                      created_at
                    )
                    VALUES (:user_id, :plan, 'razorpay', :order_id, :payment_id, :created_at)
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
                    "plan": "pro",
                    "order_id": order_id,
                    "payment_id": payment_id,
                    "created_at": created_at,
                },
            )
    except Exception:
        logger.exception("grant_pro failed")


def grant_plan(*, user_id: str, plan: str, order_id: str, payment_id: str):
    return grant_plan_with_source(
        user_id=user_id, plan=plan, order_id=order_id, payment_id=payment_id, source="razorpay"
    )


def grant_plan_with_source(*, user_id: str, plan: str, order_id: str, payment_id: str, source: str):
    plan_norm = (plan or "pro").strip().lower()
    if plan_norm not in {"starter", "pro", "business"}:
        plan_norm = "pro"
    engine = _engine()
    if not engine:
        return
    src = (source or "razorpay").strip().lower() or "razorpay"
    created_at = int(time.time())
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO subscriptions (
                      user_id,
                      plan,
                      source,
                      order_id,
                      payment_id,
                      created_at
                    )
                    VALUES (:user_id, :plan, :source, :order_id, :payment_id, :created_at)
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
                    "plan": plan_norm,
                    "source": src,
                    "order_id": order_id,
                    "payment_id": payment_id,
                    "created_at": created_at,
                },
            )
    except Exception:
        logger.exception("grant_plan failed")


def get_plan(user_id: str) -> str | None:
    engine = _engine()
    if not engine:
        return None
    try:
        state = get_subscription_state(user_id)
        if state:
            plan = _normalize_plan(state.get("plan")) or ""
            status = str(state.get("status") or "").strip().lower()
            end = state.get("current_period_end")
            now = int(time.time())
            if status in {"active", "authenticated"}:
                return plan or None
            if status in {"cancelled", "canceled"}:
                # Keep access until period end if present.
                if isinstance(end, (int, float)) and int(end) > now:
                    return plan or None
                return None
            # For unknown/halted/past_due, prefer returning the stored plan so the
            # API can decide how to gate features (e.g. grace periods).
            return plan or None

        with engine.begin() as conn:
            row = conn.execute(
                text("SELECT plan FROM subscriptions WHERE user_id = :user_id"),
                {"user_id": user_id},
            ).fetchone()
        plan = str(row[0]).lower().strip() if row and row[0] else ""
        return plan or None
    except Exception:
        logger.exception("get_plan failed")
        return None


def has_paid_plan(user_id: str) -> bool:
    plan = (get_plan(user_id) or "").strip().lower()
    return plan in {"starter", "pro", "business"}


def is_pro(user_id: str) -> bool:
    return (get_plan(user_id) or "").strip().lower() == "pro"


def get_image_usage(user_id: str) -> int:
    return int(get_usage(user_id).get("image_used", 0))


def record_image_usage(user_id: str, n: int = 1) -> int:
    return record_usage(user_id, "image_used", n=n)

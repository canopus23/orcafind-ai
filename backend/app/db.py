import os
import socket
import urllib.parse
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


def _normalize_database_url(url: str) -> str:
    """
    Railway provides DATABASE_URL. SQLAlchemy expects a dialect.
    psycopg uses `postgresql+psycopg://`.
    """
    url = (url or "").strip()
    if not url:
        return ""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _ensure_sslmode(url: str) -> str:
    """
    Supabase requires SSL/TLS. Ensure `sslmode=require` is present when the host
    looks like Supabase and the URL doesn't already specify sslmode.
    """
    try:
        parsed = urllib.parse.urlsplit(url)
        hostname = parsed.hostname or ""
        if "supabase" not in hostname.lower():
            return url
        q = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        if "sslmode" in q:
            return url
        q["sslmode"] = ["require"]
        query = urllib.parse.urlencode(q, doseq=True)
        return urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment)
        )
    except Exception:
        return url


def _maybe_force_ipv4(url: str) -> str:
    """
    Some hosts (including Supabase) can resolve to IPv6 first. If the runtime
    environment doesn't have IPv6 egress (common on some platforms), connections
    will fail with "Network is unreachable".

    When DB_FORCE_IPV4 is truthy, resolve the hostname to an IPv4 address and
    rewrite the URL host to that IP. With sslmode=require this is safe enough for
    our use (no hostname verification).
    """
    parsed = urllib.parse.urlsplit(url)
    hostname = parsed.hostname
    if not hostname:
        return url

    force_raw = (os.getenv("DB_FORCE_IPV4") or "").strip().lower()
    env = (os.getenv("ENV") or "").strip().lower()
    looks_like_supabase = "supabase" in hostname.lower()
    on_railway = any(
        (os.getenv(k) or "").strip()
        for k in (
            "RAILWAY_PROJECT_ID",
            "RAILWAY_SERVICE_ID",
            "RAILWAY_ENVIRONMENT",
            "RAILWAY_STATIC_URL",
        )
    )
    force = (
        force_raw in {"1", "true", "yes", "on"}
        or ((not force_raw) and (env in {"prod", "production"}))
        or ((not force_raw) and looks_like_supabase)
        # Railway often lacks IPv6 egress; prefer IPv4 unless explicitly disabled.
        or ((not force_raw) and on_railway)
    )
    if not force:
        return url
    # If the URL already uses an IP literal, nothing to do.
    if all(ch.isdigit() or ch == "." for ch in hostname):
        return url

    port = parsed.port or 5432
    try:
        infos = socket.getaddrinfo(hostname, port, family=socket.AF_INET, type=socket.SOCK_STREAM)
        if not infos:
            return url
        ipv4 = infos[0][4][0]
    except Exception:
        return url

    # Rebuild netloc safely: [userinfo@]host[:port]
    netloc = parsed.netloc
    if "@" in netloc:
        userinfo, hostport = netloc.rsplit("@", 1)
        userinfo = f"{userinfo}@"
    else:
        userinfo, hostport = "", netloc

    rest = ""
    if hostport.startswith("["):
        # IPv6 literal in brackets. Keep the port suffix if present.
        end = hostport.find("]")
        rest = hostport[end + 1 :] if end != -1 else ""
    else:
        # hostname[:port]
        if ":" in hostport:
            _, rest_part = hostport.split(":", 1)
            rest = f":{rest_part}"

    new_netloc = f"{userinfo}{ipv4}{rest}"
    return urllib.parse.urlunsplit(
        (parsed.scheme, new_netloc, parsed.path, parsed.query, parsed.fragment)
    )


def _maybe_db_hostaddr(url: str) -> str | None:
    """
    Returns an IPv4 address to force via libpq's `hostaddr` connection parameter.
    This is more reliable than URL rewriting in some environments, and also allows
    a manual override via DB_HOSTADDR when DNS inside the runtime is limited.
    """
    explicit = (os.getenv("DB_HOSTADDR") or "").strip()
    if explicit:
        return explicit

    parsed = urllib.parse.urlsplit(url)
    hostname = parsed.hostname
    if not hostname:
        return None

    force_raw = (os.getenv("DB_FORCE_IPV4") or "").strip().lower()
    env = (os.getenv("ENV") or "").strip().lower()
    looks_like_supabase = "supabase" in hostname.lower()
    on_railway = any(
        (os.getenv(k) or "").strip()
        for k in (
            "RAILWAY_PROJECT_ID",
            "RAILWAY_SERVICE_ID",
            "RAILWAY_ENVIRONMENT",
            "RAILWAY_STATIC_URL",
        )
    )
    force = (
        force_raw in {"1", "true", "yes", "on"}
        or ((not force_raw) and (env in {"prod", "production"}))
        or ((not force_raw) and looks_like_supabase)
        or ((not force_raw) and on_railway)
    )
    if not force:
        return None

    # Already an IPv4 literal.
    if all(ch.isdigit() or ch == "." for ch in hostname):
        return hostname

    port = parsed.port or 5432
    try:
        infos = socket.getaddrinfo(hostname, port, family=socket.AF_INET, type=socket.SOCK_STREAM)
        if not infos:
            return None
        return infos[0][4][0]
    except Exception:
        return None


def get_db_diagnostics() -> dict[str, object]:
    """
    Returns safe DB connection diagnostics (no credentials).
    Useful for debugging IPv6 egress issues on some platforms (e.g. Railway).
    """
    raw_url = os.getenv("DATABASE_URL", "") or ""
    url = _ensure_sslmode(_normalize_database_url(raw_url))
    if not url:
        return {"configured": False}
    parsed = urllib.parse.urlsplit(url)
    q = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    hostaddr = _maybe_db_hostaddr(url) or ""
    return {
        "configured": True,
        "scheme": parsed.scheme,
        "hostname": parsed.hostname or "",
        "port": int(parsed.port or 5432),
        "hostaddr": hostaddr,
        "sslmode": (q.get("sslmode") or [""])[0],
        "db_force_ipv4": (os.getenv("DB_FORCE_IPV4") or "").strip(),
        "db_hostaddr_env_set": bool((os.getenv("DB_HOSTADDR") or "").strip()),
    }


@lru_cache(maxsize=8)
def _engine_for_url(
    url: str,
    hostaddr: str,
    pool_size: int,
    max_overflow: int,
    connect_timeout: int,
) -> Engine:
    # Railway runs a long-lived service; a small pool is fine.
    connect_args: dict[str, object] = {"connect_timeout": int(connect_timeout)}
    if hostaddr:
        connect_args["hostaddr"] = hostaddr
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=int(pool_size),
        max_overflow=int(max_overflow),
        connect_args=connect_args,
    )


def get_engine() -> Engine:
    # Important: compute the final, possibly IPv4-rewritten URL first, then cache by that URL.
    # This avoids caching an engine that still resolves via IPv6 and keeps failing on platforms
    # without IPv6 egress (common on Railway).
    url = _ensure_sslmode(_normalize_database_url(os.getenv("DATABASE_URL", "")))
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    hostaddr = _maybe_db_hostaddr(url) or ""
    pool_size = int(os.getenv("DB_POOL_SIZE", "5"))
    max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    connect_timeout = int(os.getenv("DB_CONNECT_TIMEOUT", "5"))
    return _engine_for_url(url, hostaddr, pool_size, max_overflow, connect_timeout)

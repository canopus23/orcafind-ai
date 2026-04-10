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
    force = (
        force_raw in {"1", "true", "yes", "on"}
        or ((not force_raw) and (env in {"prod", "production"}))
        # Railway deployments sometimes have no IPv6 egress; Supabase commonly resolves IPv6 first.
        or ((not force_raw) and looks_like_supabase)
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

    # Replace only the hostname occurrence inside netloc.
    netloc = parsed.netloc
    if hostname in netloc:
        netloc = netloc.replace(hostname, ipv4, 1)
    return urllib.parse.urlunsplit(
        (parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment)
    )


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = _maybe_force_ipv4(_normalize_database_url(os.getenv("DATABASE_URL", "")))
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    # Railway runs a long-lived service; a small pool is fine.
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
        connect_args={"connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT", "5"))},
    )

import json
import os
from functools import lru_cache
from urllib.error import URLError
from urllib.request import urlopen

from dotenv import load_dotenv
from fastapi import HTTPException, Request
from jose import jwt

# Load environment variables from .env file
load_dotenv()

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")
SUPABASE_URL = os.getenv("SUPABASE_URL")


def _normalize_auth_header(auth_header: str) -> str:
    try:
        scheme, token = auth_header.split()
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Malformed Authorization header") from exc

    if scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authentication scheme")

    return token


@lru_cache(maxsize=8)
def _fetch_jwks(jwks_url: str) -> dict:
    with urlopen(jwks_url, timeout=5) as response:
        return json.load(response)


def _resolve_jwk(token: str) -> tuple[dict, str]:
    header = jwt.get_unverified_header(token)
    claims = jwt.get_unverified_claims(token)

    issuer = claims.get("iss")
    if not issuer and SUPABASE_URL:
        issuer = f"{SUPABASE_URL.rstrip('/')}/auth/v1"

    if not issuer:
        raise HTTPException(status_code=401, detail="Token issuer is missing")

    jwks_url = f"{issuer.rstrip('/')}/.well-known/jwks.json"

    try:
        jwks = _fetch_jwks(jwks_url)
    except (URLError, TimeoutError, ValueError) as exc:
        print(f"Failed to fetch JWKS from {jwks_url}: {exc}")
        raise HTTPException(status_code=401, detail="Unable to validate token signature") from exc

    kid = header.get("kid")
    matching_key = next((key for key in jwks.get("keys", []) if key.get("kid") == kid), None)

    if not matching_key:
        raise HTTPException(status_code=401, detail="Unable to find signing key for token")

    return matching_key, issuer


def _decode_token(token: str) -> dict:
    header = jwt.get_unverified_header(token)
    algorithm = header.get("alg")

    if not algorithm:
        raise HTTPException(status_code=401, detail="Token algorithm is missing")

    if algorithm == "HS256":
        if not SUPABASE_JWT_SECRET:
            raise HTTPException(status_code=500, detail="SUPABASE_JWT_SECRET is not configured")

        return jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )

    jwk_key, issuer = _resolve_jwk(token)
    return jwt.decode(
        token,
        jwk_key,
        algorithms=[algorithm],
        issuer=issuer,
        options={"verify_aud": False},
    )


def verify_user(request: Request):
    """
    Dependency to verify the Supabase JWT from the Authorization header.
    Expects header format: Authorization: Bearer <token>
    """
    auth_header = request.headers.get("Authorization")

    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    token = _normalize_auth_header(auth_header)

    try:
        return _decode_token(token)
    except HTTPException:
        raise
    except Exception as exc:
        print(f"JWT verification error: {exc}")
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

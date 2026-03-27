from fastapi import Request, HTTPException
from jose import jwt
from app.core.config import SUPABASE_JWT_SECRET


def verify_user(request: Request):
    auth_header = request.headers.get("Authorization")

    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing token")

    try:
        token = auth_header.split(" ")[1]

        print("SECRET:", SUPABASE_JWT_SECRET[:10])  # debug

        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False}
        )

        return payload

    except Exception as e:
        print("JWT ERROR:", e)
        raise HTTPException(status_code=401, detail="Invalid token")
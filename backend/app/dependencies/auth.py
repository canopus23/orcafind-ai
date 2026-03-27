import os
from fastapi import Request, HTTPException
from jose import jwt
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Ensure this matches the JWT Secret in your Supabase Dashboard (Settings -> API)
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")

def verify_user(request: Request):
    """
    Dependency to verify the Supabase JWT from the Authorization header.
    Expects header format: Authorization: Bearer <token>
    """
    auth_header = request.headers.get("Authorization")
    
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing Authorization Header")
    
    try:
        # Split 'Bearer' from the actual token string
        scheme, token = auth_header.split()
        if scheme.lower() != 'bearer':
            raise HTTPException(status_code=401, detail="Invalid authentication scheme")
            
        # Decode and verify the token
        # verify_aud is set to False because Supabase tokens often use 'authenticated' as the audience
        payload = jwt.decode(
            token, 
            SUPABASE_JWT_SECRET, 
            algorithms=["HS256"], 
            options={"verify_aud": False}
        )
        return payload
    except Exception as e:
        print(f"JWT Verification Error: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")
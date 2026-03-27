import os
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Ensure these imports match the actual file paths and function names
from app.dependencies.auth import verify_user
from app.services.ai_service import generate_social_content

app = FastAPI(title="OrcaFind AI API")

# Define allowed origins explicitly for CORS with credentials.
# Browsers block wildcard "*" when an Authorization header is present.
origins = [
    "https://orcafind.com",
    "https://www.orcafind.com",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# CORSMiddleware must be added first to handle preflight OPTIONS requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True, # Required to allow Authorization headers
    allow_methods=["*"],    # Allows GET, POST, OPTIONS, etc.
    allow_headers=["*"],    # Allows Content-Type, Authorization, etc.
)

# Define the expected JSON body for the request
class ContentRequest(BaseModel):
    text: str

@app.get("/")
async def root():
    return {"status": "online", "message": "OrcaFind API is operational"}

@app.post("/repurpose/")
async def repurpose_content(req: ContentRequest, user=Depends(verify_user)):
    """
    Protected endpoint. 'verify_user' will raise a 401 if the JWT is invalid.
    """
    try:
        # Input validation
        if not req.text.strip():
            raise HTTPException(status_code=400, detail="Input text cannot be empty")
            
        # Process content via AI service
        result = generate_social_content(req.text)
        return {"result": result}
        
    except Exception as e:
        # Log the error to the server console for debugging
        print(f"Error in /repurpose/: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error during content generation")

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
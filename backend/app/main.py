from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.dependencies.auth import verify_user
from app.services.ai_service import generate_social_content
from pydantic import BaseModel

app = FastAPI(title="OrcaFind AI API")

# CORS configuration: Adjust 'allow_origins' to your specific frontend URL in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RepurposeRequest(BaseModel):
    text: str

@app.get("/")
async def root():
    return {"message": "OrcaFind API is running"}

@app.post("/repurpose/")
async def repurpose_content(request: RepurposeRequest, user=Depends(verify_user)):
    """
    Protected endpoint that generates social media content.
    The 'user' parameter is populated by verify_user if the token is valid.
    """
    try:
        # Input validation
        if not request.text.strip():
            raise HTTPException(status_code=400, detail="Text content cannot be empty")
            
        # Call the AI service to process the text
        result = generate_social_content(request.text)
        return {"result": result}
        
    except Exception as e:
        print(f"Processing Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error during content generation")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
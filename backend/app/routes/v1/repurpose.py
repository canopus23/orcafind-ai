from fastapi import APIRouter
from models.request import ContentRequest
from services.ai_service import generate_content

router = APIRouter()

@router.post("/")
def repurpose(req: ContentRequest):
    result = generate_content(req.text)
    return {"result": result}
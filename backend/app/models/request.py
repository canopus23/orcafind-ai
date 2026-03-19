from pydantic import BaseModel

class ContentRequest(BaseModel):
    text: str
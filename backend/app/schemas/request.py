from pydantic import BaseModel

class ContentRequest(BaseModel):
    text: str
    x_style: str = "thread"   # "single" | "thread"
    format: str = "professional"

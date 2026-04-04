from pydantic import BaseModel, Field
from typing import Optional


class CompletePostRequest(BaseModel):
    text: str = Field(min_length=1, max_length=12000)
    x_style: str = Field(default="single", max_length=16)  # single | thread
    format: str = Field(default="professional", max_length=32)

    image_brief: Optional[str] = Field(default=None, max_length=1200)
    image_style: Optional[str] = Field(default=None, max_length=64)
    image_aspect: str = Field(default="square", max_length=32)
    image_count: int = Field(default=1, ge=1, le=1)


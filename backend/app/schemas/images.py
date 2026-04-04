from pydantic import BaseModel, Field


class ImageGenerateRequest(BaseModel):
    brief: str = Field(min_length=1, max_length=2000)
    style: str = Field(default="saas_minimal", max_length=64)
    aspect: str = Field(default="square", max_length=32)  # square | portrait | landscape
    count: int = Field(default=3, ge=1, le=6)


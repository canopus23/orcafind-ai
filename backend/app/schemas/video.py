from pydantic import BaseModel, HttpUrl, Field


class VideoShortsRequest(BaseModel):
    youtube_url: HttpUrl
    duration_seconds: int = Field(default=30, ge=10, le=90)
    style: str = Field(default="captioned")
    platform: str = Field(default="shorts")
    captions: bool = Field(default=True)


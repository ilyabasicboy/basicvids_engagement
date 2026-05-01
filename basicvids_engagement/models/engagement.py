from pydantic import BaseModel, ConfigDict, Field as PydanticField


class VideoReactionChange(BaseModel):
    reaction: str = PydanticField(pattern="^(like|dislike|none)$")


class VideoViewCreate(BaseModel):
    watched_seconds: float | None = PydanticField(default=None, ge=0)


class VideoEngagementSummaryPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    video_id: str
    likes_count: int
    dislikes_count: int
    views_count: int
    user_reaction: str | None = None


class VideoEngagementBatchRequest(BaseModel):
    video_ids: list[str] = PydanticField(min_length=1, max_length=100)


class VideoEngagementBatchResponse(BaseModel):
    items: list[VideoEngagementSummaryPublic]

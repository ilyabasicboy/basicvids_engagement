from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class VideoEngagement(SQLModel, table=True):
    video_id: str = Field(primary_key=True, max_length=100)
    likes_count: int = Field(default=0, ge=0)
    dislikes_count: int = Field(default=0, ge=0)
    views_count: int = Field(default=0, ge=0)
    created_at: datetime = Field(
        sa_type=DateTime(timezone=True),
        default_factory=utc_now,
        nullable=False,
    )
    updated_at: datetime = Field(
        sa_type=DateTime(timezone=True),
        default_factory=utc_now,
        nullable=False,
    )


class VideoReaction(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("video_id", "user_id", name="uq_video_reaction_video_user"),)

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    video_id: str = Field(index=True, max_length=100)
    user_id: int = Field(index=True)
    reaction: str = Field(max_length=10)
    created_at: datetime = Field(
        sa_type=DateTime(timezone=True),
        default_factory=utc_now,
        nullable=False,
    )
    updated_at: datetime = Field(
        sa_type=DateTime(timezone=True),
        default_factory=utc_now,
        nullable=False,
    )

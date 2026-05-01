from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session, col, select

from basicvids_engagement.auth import CurrentUser, get_current_user, get_optional_current_user
from basicvids_engagement.db import get_session
from basicvids_engagement.models.engagement import (
    VideoEngagementBatchRequest,
    VideoEngagementBatchResponse,
    VideoEngagementSummaryPublic,
    VideoReactionChange,
    VideoViewCreate,
)
from basicvids_engagement.rate_limit import client_identifier, enforce_rate_limit
from basicvids_engagement.schemas.engagement import VideoEngagement, VideoReaction


router = APIRouter(tags=["Engagement"], prefix="/engagement")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_or_create_video_engagement(session: Session, video_id: str) -> VideoEngagement:
    engagement = session.get(VideoEngagement, video_id)
    if engagement:
        return engagement

    engagement = VideoEngagement(video_id=video_id)
    session.add(engagement)
    session.flush()
    return engagement


def build_summary(
    engagement: VideoEngagement | None,
    video_id: str,
    user_reaction: str | None = None,
) -> VideoEngagementSummaryPublic:
    return VideoEngagementSummaryPublic(
        video_id=video_id,
        likes_count=engagement.likes_count if engagement else 0,
        dislikes_count=engagement.dislikes_count if engagement else 0,
        views_count=engagement.views_count if engagement else 0,
        user_reaction=user_reaction,
    )


def get_user_reaction(session: Session, video_id: str, user_id: int) -> VideoReaction | None:
    return session.exec(
        select(VideoReaction).where(
            VideoReaction.video_id == video_id,
            VideoReaction.user_id == user_id,
        )
    ).first()


@router.get("/videos/{video_id}", response_model=VideoEngagementSummaryPublic)
async def get_video_engagement(
    video_id: str,
    session: Session = Depends(get_session),
    current_user: CurrentUser | None = Depends(get_optional_current_user),
) -> VideoEngagementSummaryPublic:
    engagement = session.get(VideoEngagement, video_id)
    reaction = get_user_reaction(session, video_id, current_user.id) if current_user else None
    return build_summary(engagement, video_id, reaction.reaction if reaction else None)


@router.post("/videos/summaries", response_model=VideoEngagementBatchResponse)
async def get_video_engagement_batch(
    data: VideoEngagementBatchRequest,
    session: Session = Depends(get_session),
    current_user: CurrentUser | None = Depends(get_optional_current_user),
) -> VideoEngagementBatchResponse:
    ordered_video_ids = list(dict.fromkeys(video_id.strip() for video_id in data.video_ids if video_id.strip()))
    if not ordered_video_ids:
        return VideoEngagementBatchResponse(items=[])

    engagements = session.exec(select(VideoEngagement).where(col(VideoEngagement.video_id).in_(ordered_video_ids))).all()
    engagement_by_video_id = {engagement.video_id: engagement for engagement in engagements}

    reaction_by_video_id = {}
    if current_user:
        reactions = session.exec(
            select(VideoReaction).where(
                col(VideoReaction.video_id).in_(ordered_video_ids),
                VideoReaction.user_id == current_user.id,
            )
        ).all()
        reaction_by_video_id = {reaction.video_id: reaction.reaction for reaction in reactions}

    return VideoEngagementBatchResponse(
        items=[
            build_summary(
                engagement_by_video_id.get(video_id),
                video_id,
                reaction_by_video_id.get(video_id),
            )
            for video_id in ordered_video_ids
        ]
    )


@router.put("/videos/{video_id}/reaction", response_model=VideoEngagementSummaryPublic)
async def set_video_reaction(
    video_id: str,
    data: VideoReactionChange,
    request: Request,
    session: Session = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> VideoEngagementSummaryPublic:
    await enforce_rate_limit("set_reaction_ip", client_identifier(request), 120, 60)
    await enforce_rate_limit("set_reaction_user", f"user:{current_user.id}", 120, 60)

    normalized_reaction = data.reaction.strip().lower()
    reaction = get_user_reaction(session, video_id, current_user.id)
    engagement = get_or_create_video_engagement(session, video_id)
    now = utc_now()

    if reaction and reaction.reaction == normalized_reaction:
        return build_summary(engagement, video_id, reaction.reaction)

    if reaction:
        if reaction.reaction == "like":
            engagement.likes_count = max(0, engagement.likes_count - 1)
        elif reaction.reaction == "dislike":
            engagement.dislikes_count = max(0, engagement.dislikes_count - 1)

    if normalized_reaction == "none":
        if reaction:
            session.delete(reaction)
        engagement.updated_at = now
        session.add(engagement)
        session.commit()
        session.refresh(engagement)
        return build_summary(engagement, video_id, None)

    if not reaction:
        reaction = VideoReaction(
            video_id=video_id,
            user_id=current_user.id,
            reaction=normalized_reaction,
        )

    reaction.reaction = normalized_reaction
    reaction.updated_at = now
    session.add(reaction)

    if normalized_reaction == "like":
        engagement.likes_count += 1
    elif normalized_reaction == "dislike":
        engagement.dislikes_count += 1

    engagement.updated_at = now
    session.add(engagement)
    session.commit()
    session.refresh(engagement)
    return build_summary(engagement, video_id, normalized_reaction)


@router.post("/videos/{video_id}/view", response_model=VideoEngagementSummaryPublic, status_code=201)
async def register_video_view(
    video_id: str,
    data: VideoViewCreate,
    request: Request,
    session: Session = Depends(get_session),
    current_user: CurrentUser | None = Depends(get_optional_current_user),
) -> VideoEngagementSummaryPublic:
    await enforce_rate_limit("register_view_ip", f"{client_identifier(request)}:{video_id}", 30, 60)

    engagement = get_or_create_video_engagement(session, video_id)
    engagement.views_count += 1
    engagement.updated_at = utc_now()
    session.add(engagement)
    session.commit()
    session.refresh(engagement)

    reaction = get_user_reaction(session, video_id, current_user.id) if current_user else None
    return build_summary(engagement, video_id, reaction.reaction if reaction else None)

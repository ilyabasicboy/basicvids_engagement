from sqlmodel import Session, delete
import httpx
import pytest

from basicvids_engagement.auth import CurrentUser, get_current_user, get_optional_current_user
from basicvids_engagement.schemas.engagement import VideoEngagement, VideoReaction
from basicvids_engagement.tests import app, engine


pytestmark = pytest.mark.anyio


async def request(method: str, url: str, **kwargs):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, url, **kwargs)


def user(user_id: int = 1, is_admin: bool = False) -> CurrentUser:
    return CurrentUser(
        id=user_id,
        username=f"user-{user_id}",
        first_name="Test",
        last_name="Viewer",
        email=f"user-{user_id}@example.com",
        is_admin=is_admin,
        email_confirmed=True,
    )


def set_current_user(current_user: CurrentUser) -> None:
    async def override_get_current_user():
        return current_user

    async def override_get_optional_current_user():
        return current_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_optional_current_user] = override_get_optional_current_user


def clear_auth_overrides() -> None:
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_optional_current_user, None)


class BaseTestEngagement:
    def setup_method(self):
        set_current_user(user())
        with Session(engine) as session:
            session.exec(delete(VideoReaction))
            session.exec(delete(VideoEngagement))
            session.commit()


class TestEngagement(BaseTestEngagement):
    async def test_get_empty_summary(self):
        response = await request("GET", "/api/v1/engagement/videos/video-1")

        assert response.status_code == 200
        assert response.json() == {
            "video_id": "video-1",
            "likes_count": 0,
            "dislikes_count": 0,
            "views_count": 0,
            "user_reaction": None,
        }

    async def test_set_like_creates_reaction(self):
        response = await request(
            "PUT",
            "/api/v1/engagement/videos/video-1/reaction",
            json={"reaction": "like"},
        )

        assert response.status_code == 200
        assert response.json() == {
            "video_id": "video-1",
            "likes_count": 1,
            "dislikes_count": 0,
            "views_count": 0,
            "user_reaction": "like",
        }

    async def test_switch_like_to_dislike_updates_counts(self):
        await request("PUT", "/api/v1/engagement/videos/video-1/reaction", json={"reaction": "like"})

        response = await request(
            "PUT",
            "/api/v1/engagement/videos/video-1/reaction",
            json={"reaction": "dislike"},
        )

        assert response.status_code == 200
        assert response.json()["likes_count"] == 0
        assert response.json()["dislikes_count"] == 1
        assert response.json()["user_reaction"] == "dislike"

    async def test_remove_reaction(self):
        await request("PUT", "/api/v1/engagement/videos/video-1/reaction", json={"reaction": "dislike"})

        response = await request(
            "PUT",
            "/api/v1/engagement/videos/video-1/reaction",
            json={"reaction": "none"},
        )

        assert response.status_code == 200
        assert response.json()["likes_count"] == 0
        assert response.json()["dislikes_count"] == 0
        assert response.json()["user_reaction"] is None

    async def test_set_reaction_requires_authentication(self):
        clear_auth_overrides()

        response = await request(
            "PUT",
            "/api/v1/engagement/videos/video-1/reaction",
            json={"reaction": "like"},
        )

        assert response.status_code == 401

    async def test_register_view_increments_count(self):
        response = await request(
            "POST",
            "/api/v1/engagement/videos/video-1/view",
            json={"watched_seconds": 12},
        )

        assert response.status_code == 201
        assert response.json()["views_count"] == 1
        assert response.json()["likes_count"] == 0
        assert response.json()["dislikes_count"] == 0

    async def test_batch_summary_returns_requested_order(self):
        await request("PUT", "/api/v1/engagement/videos/video-2/reaction", json={"reaction": "like"})
        await request("POST", "/api/v1/engagement/videos/video-1/view", json={})

        response = await request(
            "POST",
            "/api/v1/engagement/videos/summaries",
            json={"video_ids": ["video-1", "video-2", "video-3"]},
        )

        assert response.status_code == 200
        assert response.json()["items"] == [
            {
                "video_id": "video-1",
                "likes_count": 0,
                "dislikes_count": 0,
                "views_count": 1,
                "user_reaction": None,
            },
            {
                "video_id": "video-2",
                "likes_count": 1,
                "dislikes_count": 0,
                "views_count": 0,
                "user_reaction": "like",
            },
            {
                "video_id": "video-3",
                "likes_count": 0,
                "dislikes_count": 0,
                "views_count": 0,
                "user_reaction": None,
            },
        ]

    async def test_summary_is_public_without_auth(self):
        clear_auth_overrides()
        with Session(engine) as session:
            session.add(VideoEngagement(video_id="video-1", likes_count=3, dislikes_count=1, views_count=10))
            session.commit()

        response = await request("GET", "/api/v1/engagement/videos/video-1")

        assert response.status_code == 200
        assert response.json()["user_reaction"] is None
        assert response.json()["views_count"] == 10

    async def test_summary_includes_current_user_reaction(self):
        await request("PUT", "/api/v1/engagement/videos/video-1/reaction", json={"reaction": "like"})

        response = await request("GET", "/api/v1/engagement/videos/video-1")

        assert response.status_code == 200
        assert response.json()["user_reaction"] == "like"

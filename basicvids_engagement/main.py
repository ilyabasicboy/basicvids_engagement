from contextlib import asynccontextmanager

from fastapi import FastAPI

from basicvids_engagement.db import create_db_and_tables
from basicvids_engagement.routers.engagement import router as engagement_router
from basicvids_engagement.routers.root import router as root_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(title="BasicVids Engagement", lifespan=lifespan)

app.include_router(engagement_router, prefix="/api/v1")
app.include_router(root_router)

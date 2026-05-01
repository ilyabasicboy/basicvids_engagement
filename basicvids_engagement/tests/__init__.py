from basicvids_engagement.db import create_db_and_tables, engine
from basicvids_engagement.main import app

create_db_and_tables()

__all__ = ["app", "engine"]

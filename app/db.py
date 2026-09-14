from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import DATA_DIR, env
from app.models import Base

engine = None
SessionLocal = None


def init_db(database_url: str | None = None) -> None:
    global engine, SessionLocal
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    url = database_url or env.database_url
    engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    _ensure_schema()


def _ensure_schema() -> None:
    if engine is None:
        return
    with engine.begin() as conn:
        page_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(pages)")).fetchall()}
        if page_cols and "page_type" not in page_cols:
            conn.execute(text("ALTER TABLE pages ADD COLUMN page_type VARCHAR(20) DEFAULT 'html'"))
            conn.execute(text("UPDATE pages SET page_type = 'html' WHERE page_type IS NULL"))


def get_db() -> Generator[Session, None, None]:
    if SessionLocal is None:
        init_db()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

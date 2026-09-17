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
    from app.services.users import migrate_multi_user

    migrate_multi_user()


def _ensure_schema() -> None:
    if engine is None:
        return
    with engine.begin() as conn:
        page_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(pages)")).fetchall()}
        if page_cols and "page_type" not in page_cols:
            conn.execute(text("ALTER TABLE pages ADD COLUMN page_type VARCHAR(20) DEFAULT 'html'"))
            conn.execute(text("UPDATE pages SET page_type = 'html' WHERE page_type IS NULL"))
        if page_cols and "auth_username" not in page_cols:
            conn.execute(text("ALTER TABLE pages ADD COLUMN auth_username VARCHAR(200) DEFAULT ''"))
        if page_cols and "auth_password_hash" not in page_cols:
            conn.execute(text("ALTER TABLE pages ADD COLUMN auth_password_hash TEXT DEFAULT ''"))
        if page_cols and "expires_at" not in page_cols:
            conn.execute(text("ALTER TABLE pages ADD COLUMN expires_at DATETIME"))
        if page_cols and "enabled" not in page_cols:
            conn.execute(text("ALTER TABLE pages ADD COLUMN enabled BOOLEAN DEFAULT 1"))
            conn.execute(text("UPDATE pages SET enabled = 1 WHERE enabled IS NULL"))
        if page_cols and "description" not in page_cols:
            conn.execute(text("ALTER TABLE pages ADD COLUMN description TEXT DEFAULT ''"))
            conn.execute(text("UPDATE pages SET description = '' WHERE description IS NULL"))
        if page_cols and "open_count" not in page_cols:
            conn.execute(text("ALTER TABLE pages ADD COLUMN open_count INTEGER DEFAULT 0"))
            conn.execute(text("UPDATE pages SET open_count = 0 WHERE open_count IS NULL"))
        if page_cols and "last_opened_at" not in page_cols:
            conn.execute(text("ALTER TABLE pages ADD COLUMN last_opened_at DATETIME"))
        if page_cols and "user_id" not in page_cols:
            conn.execute(text("ALTER TABLE pages ADD COLUMN user_id INTEGER"))
        # Rebuild pages if the old global UNIQUE(slug) still exists so (user_id, slug) can collide across users.
        indexes = conn.execute(text("PRAGMA index_list(pages)")).fetchall()
        for index in indexes:
            # row: seq, name, unique, origin, partial
            if not index[2]:
                continue
            name = index[1]
            cols = [row[2] for row in conn.execute(text(f"PRAGMA index_info('{name}')")).fetchall()]
            if cols == ["slug"]:
                conn.execute(text("DROP INDEX IF EXISTS " + name))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_pages_user_slug ON pages(user_id, slug)"))


def get_db() -> Generator[Session, None, None]:
    if SessionLocal is None:
        init_db()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

"""
app/core/database.py
Database connection engine, session management, and table initializer.

Uses SQLite with foreign key enforcement enabled, and provides clean
context-managed sessions for transactions.
"""

from contextlib import contextmanager
from typing import Generator, Optional
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import console, settings
from app.models.schema import Base

# Configure SQLAlchemy engine
# connect_args={"check_same_thread": False} is required for SQLite across multi-threaded contexts
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
    echo=False,
)


# Enforce foreign key constraints in SQLite (disabled by default in SQLite)
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if "sqlite" in settings.database_url:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# Thread-safe session maker
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db(custom_engine: Optional[Engine] = None) -> None:
    """
    Initialize all database tables defined in app.models.schema.
    Idempotent: safe to run on application startup or in test suites.
    """
    target_engine = custom_engine or engine
    Base.metadata.create_all(bind=target_engine)

    # Ensure backward-compatible column migrations in SQLite tables
    if "sqlite" in str(target_engine.url):
        try:
            with target_engine.connect() as conn:
                # Videos table migrations
                cursor = conn.execute(text("PRAGMA table_info(videos)"))
                cols = [r[1] for r in cursor.fetchall()]
                if "source_url" not in cols:
                    conn.execute(text("ALTER TABLE videos ADD COLUMN source_url TEXT"))

                # Styles table migrations
                cursor_styles = conn.execute(text("PRAGMA table_info(styles)"))
                style_cols = [r[1] for r in cursor_styles.fetchall()]
                if "user_id" not in style_cols:
                    conn.execute(text("ALTER TABLE styles ADD COLUMN user_id VARCHAR(64)"))
                if "name" not in style_cols:
                    conn.execute(text("ALTER TABLE styles ADD COLUMN name VARCHAR(128)"))
                if "description" not in style_cols:
                    conn.execute(text("ALTER TABLE styles ADD COLUMN description TEXT"))

                conn.commit()
        except Exception:
            pass

    console.print(
        f"[bold green][DB INITIALIZED][/bold green] Database schema ready at: "
        f"[cyan]{target_engine.url}[/cyan]"
    )


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager providing a transactional database session.
    Automatically commits on success or rolls back on exception.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as exc:
        session.rollback()
        raise exc
    finally:
        session.close()


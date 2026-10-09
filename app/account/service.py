"""
app/account/service.py
Account, Creator Profile, and History Management Service.

Provides user onboarding, multi-creator organization, and upload/script history.
Future-proofed for OAuth providers (Google, Clerk, Auth0) while operating locally
in pilot mode.
"""

import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from app.core.config import console, settings
from app.core.database import get_db_session
from app.models.schema import Script, Style, StyleReference, User, Video, VideoMemory, utc_now

SESSION_FILE = settings.data_dir / ".current_user"


def get_current_user_id(session_file: Optional[Path] = None) -> Optional[str]:
    """Return the active user_id from the local session file if present, else None."""
    target_file = session_file or SESSION_FILE
    if target_file.is_file():
        saved = target_file.read_text(encoding="utf-8").strip()
        if saved:
            return saved
    return None


def set_current_user_id(user_id: str, session_file: Optional[Path] = None) -> None:
    """Save the active user_id to the local session file."""
    target_file = session_file or SESSION_FILE
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(user_id.strip(), encoding="utf-8")


def clear_current_session(session_file: Optional[Path] = None) -> None:
    """Clear the active user session file."""
    target_file = session_file or SESSION_FILE
    if target_file.is_file():
        target_file.unlink(missing_ok=True)


def get_authenticated_user(session_file: Optional[Path] = None) -> User:
    """
    Retrieve the currently authenticated User instance from the local session.
    Raises PermissionError if no user session is active or the user is not found in DB.
    """
    uid = get_current_user_id(session_file=session_file)
    if not uid:
        raise PermissionError(
            "Access Denied: No user is currently logged in.\n"
            "Please log in using: python -m app.cli user login <username>"
        )

    with get_db_session() as session:
        user = session.query(User).filter_by(user_id=uid).first()
        if not user:
            raise PermissionError(
                f"Access Denied: Logged-in user '{uid}' was not found in the database.\n"
                f"Please log in using: python -m app.cli user login <username>"
            )
        _ = (user.user_id, user.username, user.email, user.auth_provider)
        session.expunge(user)
        return user


def slugify(text: str) -> str:
    """Generate a clean URL/ID slug from a human-readable name."""
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text.strip("_") or "creator"


class AccountService:
    """
    Service managing User accounts, Creator profiles (styles), and historical records.
    """

    def get_authenticated_user(self, session_file: Optional[Path] = None) -> User:
        """Retrieve the currently authenticated user from session or raise PermissionError."""
        return get_authenticated_user(session_file=session_file)

    def login(
        self,
        username: str,
        email: Optional[str] = None,
        auth_provider: str = "local",
        session_file: Optional[Path] = None,
    ) -> User:
        """Retrieve or create user and set local active session."""
        user = self.create_or_get_user(username=username, email=email, auth_provider=auth_provider)
        set_current_user_id(user.user_id, session_file=session_file)
        return user

    def create_or_get_user(
        self,
        username: str,
        email: Optional[str] = None,
        auth_provider: str = "local",
    ) -> User:
        """
        Retrieve an existing user by username or register a new user.
        Future-proofed: accepts optional email and OAuth auth_provider.
        """
        clean_name = username.strip().lower()
        if not clean_name:
            raise ValueError("Username cannot be empty.")

        with get_db_session() as session:
            user = session.query(User).filter_by(username=clean_name).first()
            if not user:
                user_id = f"usr_{slugify(clean_name)}"
                user = User(
                    user_id=user_id,
                    username=clean_name,
                    email=email.strip().lower() if email else None,
                    auth_provider=auth_provider,
                    created_at=utc_now(),
                )
                session.add(user)
                session.flush()
                console.print(f"[bold green]Registered new user:[/bold green] [cyan]{clean_name}[/cyan] ({user_id})")

            _ = (user.user_id, user.username, user.email, user.auth_provider)
            session.expunge(user)
            return user

    def create_creator(
        self,
        user_id: str,
        creator_name: str,
        creator_id: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Style:
        """
        Register a new Creator profile (represented as a Style in core architecture).
        """
        clean_name = creator_name.strip()
        if not clean_name:
            raise ValueError("Creator name cannot be empty.")

        target_id = creator_id or f"c_{slugify(clean_name)}"

        with get_db_session() as session:
            existing = session.query(Style).filter_by(style_id=target_id).first()
            if existing:
                # Update existing creator display name and ownership if unassigned
                existing.name = clean_name
                if description:
                    existing.description = description
                if not existing.user_id:
                    existing.user_id = user_id
                session.flush()
                _ = (existing.style_id, existing.name, existing.user_id, existing.version)
                session.expunge(existing)
                return existing

            new_creator = Style(
                style_id=target_id,
                user_id=user_id,
                name=clean_name,
                description=description,
                version=1,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
            session.add(new_creator)
            session.flush()
            _ = (new_creator.style_id, new_creator.name, new_creator.user_id, new_creator.version)
            session.expunge(new_creator)

        console.print(
            f"[bold green]Added creator profile:[/bold green] '[cyan]{clean_name}[/cyan]' (ID: {target_id})"
        )
        return new_creator

    def list_creators(self, user_id: Optional[str] = None) -> List[Style]:
        """List all creators, optionally filtered by user_id."""
        with get_db_session() as session:
            query = session.query(Style)
            if user_id:
                query = query.filter_by(user_id=user_id)
            creators = query.order_by(Style.created_at.desc()).all()
            result = []
            for c in creators:
                _ = (c.style_id, c.name, c.user_id, c.version, c.bible_text)
                session.expunge(c)
                result.append(c)
            return result

    def get_creator(self, style_id: str) -> Optional[Style]:
        """Fetch a specific creator/style by ID."""
        with get_db_session() as session:
            creator = session.query(Style).filter_by(style_id=style_id).first()
            if creator:
                _ = (creator.style_id, creator.name, creator.user_id, creator.version, creator.bible_text)
                session.expunge(creator)
                return creator
        return None

    def get_creator_upload_history(self, style_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve upload and indexing history for all videos associated with a creator.
        """
        with get_db_session() as session:
            # Query videos linked to style via StyleReference
            refs = (
                session.query(StyleReference, Video)
                .join(Video, StyleReference.video_id == Video.video_id)
                .filter(StyleReference.style_id == style_id)
                .order_by(Video.created_at.desc())
                .all()
            )

            history = []
            for ref, vid in refs:
                history.append(
                    {
                        "video_id": vid.video_id,
                        "source_url": vid.source_url or "Local File",
                        "status": vid.status,
                        "duration_ms": vid.duration_ms,
                        "storage_uri": vid.storage_uri,
                        "audio_uri": vid.audio_uri,
                        "created_at": vid.created_at.isoformat() if vid.created_at else None,
                    }
                )
            return history

    def get_user_script_history(
        self,
        user_id: Optional[str] = None,
        style_id: Optional[str] = None,
    ) -> List[Script]:
        """
        Retrieve history of all generated scripts for a user or creator.
        """
        with get_db_session() as session:
            query = session.query(Script)
            if user_id:
                query = query.filter_by(user_id=user_id)
            if style_id:
                query = query.filter_by(style_id=style_id)
            scripts = query.order_by(Script.created_at.desc()).all()
            result = []
            for s in scripts:
                _ = (s.script_id, s.user_id, s.style_id, s.premise, s.script_text, s.created_at)
                session.expunge(s)
                result.append(s)
            return result


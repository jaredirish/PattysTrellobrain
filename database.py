"""
SQLite Database Manager for Patty's Knowledge Brain

Handles persistent storage of:
- Synced Trello cards
- Uploaded documents
- Chat history
- Sync metadata
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

# Default database location
DEFAULT_DB_PATH = Path(__file__).parent / "knowledge_brain.db"


class DatabaseManager:
    """Manages SQLite database operations for the Knowledge Brain."""

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize the database manager."""
        self.db_path = db_path or DEFAULT_DB_PATH
        self._init_database()

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_database(self):
        """Create database tables if they don't exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Trello cards table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trello_cards (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    board_name TEXT,
                    list_name TEXT,
                    labels TEXT,
                    comments TEXT,
                    url TEXT,
                    last_activity TIMESTAMP,
                    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    content_text TEXT
                )
            """)

            # Uploaded documents table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    file_type TEXT,
                    content_text TEXT,
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    file_hash TEXT UNIQUE
                )
            """)

            # Chat history table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Sync metadata table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sync_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Client profiles table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS clients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    business_type TEXT,
                    target_audience TEXT,
                    key_offerings TEXT,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Cast Magic transcripts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS castmagic_transcripts (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    source_url TEXT,
                    status TEXT,
                    duration_seconds REAL,
                    language TEXT,
                    transcript_text TEXT,
                    content_text TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create indexes for faster searches
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_cards_board
                ON trello_cards(board_name)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_cards_synced
                ON trello_cards(synced_at)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_castmagic_synced
                ON castmagic_transcripts(synced_at)
            """)

    # --- Trello Cards ---

    def upsert_trello_card(self, card_id: str, name: str, description: str,
                           board_name: str, list_name: str, labels: list[str],
                           comments: list[str], url: str, last_activity: datetime,
                           content_text: str):
        """Insert or update a Trello card."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO trello_cards
                (id, name, description, board_name, list_name, labels, comments,
                 url, last_activity, synced_at, content_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
            """, (
                card_id, name, description, board_name, list_name,
                json.dumps(labels), json.dumps(comments), url,
                last_activity.isoformat() if last_activity else None,
                content_text
            ))

    def get_all_trello_content(self) -> str:
        """Get all Trello card content as a combined text string."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT content_text FROM trello_cards ORDER BY board_name, list_name")
            rows = cursor.fetchall()
            return "\n\n".join(row["content_text"] for row in rows if row["content_text"])

    def get_trello_card_count(self) -> int:
        """Get the total number of Trello cards."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM trello_cards")
            return cursor.fetchone()["count"]

    def get_board_summary(self) -> list[dict]:
        """Get a summary of cards per board."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT board_name, COUNT(*) as card_count
                FROM trello_cards
                GROUP BY board_name
                ORDER BY card_count DESC
            """)
            return [dict(row) for row in cursor.fetchall()]

    def clear_trello_cards(self):
        """Delete all Trello cards (for full re-sync)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM trello_cards")

    # --- Documents ---

    def add_document(self, filename: str, file_type: str, content_text: str, file_hash: str) -> bool:
        """
        Add an uploaded document.

        Returns True if added, False if already exists.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO documents (filename, file_type, content_text, file_hash)
                    VALUES (?, ?, ?, ?)
                """, (filename, file_type, content_text, file_hash))
            return True
        except sqlite3.IntegrityError:
            return False  # Document already exists

    def get_all_document_content(self) -> str:
        """Get all document content as a combined text string."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT filename, content_text FROM documents ORDER BY uploaded_at")
            rows = cursor.fetchall()
            parts = []
            for row in rows:
                parts.append(f"--- DOCUMENT: {row['filename']} ---\n{row['content_text']}")
            return "\n\n".join(parts)

    def get_document_count(self) -> int:
        """Get the total number of uploaded documents."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM documents")
            return cursor.fetchone()["count"]

    def clear_documents(self):
        """Delete all uploaded documents."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM documents")

    # --- Chat History ---

    def add_chat_message(self, role: str, content: str):
        """Add a message to chat history."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO chat_history (role, content)
                VALUES (?, ?)
            """, (role, content))

    def get_chat_history(self, limit: int = 100) -> list[dict]:
        """Get recent chat history."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT role, content, created_at
                FROM chat_history
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [dict(row) for row in reversed(rows)]

    def clear_chat_history(self):
        """Clear all chat history."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM chat_history")

    # --- Sync Metadata ---

    def set_metadata(self, key: str, value: str):
        """Set a metadata value."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO sync_metadata (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """, (key, value))

    def get_metadata(self, key: str) -> Optional[str]:
        """Get a metadata value."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM sync_metadata WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else None

    def get_last_sync_time(self) -> Optional[datetime]:
        """Get the last Trello sync timestamp."""
        value = self.get_metadata("last_trello_sync")
        if value:
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None

    def set_last_sync_time(self, sync_time: Optional[datetime] = None):
        """Set the last Trello sync timestamp."""
        if sync_time is None:
            sync_time = datetime.now()
        self.set_metadata("last_trello_sync", sync_time.isoformat())

    # --- Combined Content ---

    def get_all_content(self) -> str:
        """Get all content (Trello + Documents + Cast Magic) as a combined string."""
        trello_content = self.get_all_trello_content()
        doc_content = self.get_all_document_content()
        castmagic_content = self.get_all_castmagic_content()

        parts = []
        if trello_content:
            parts.append("=== TRELLO CONTENT ===\n" + trello_content)
        if doc_content:
            parts.append("=== UPLOADED DOCUMENTS ===\n" + doc_content)
        if castmagic_content:
            parts.append("=== CAST MAGIC TRANSCRIPTS ===\n" + castmagic_content)

        return "\n\n".join(parts)

    def get_stats(self) -> dict:
        """Get database statistics."""
        return {
            "trello_cards": self.get_trello_card_count(),
            "documents": self.get_document_count(),
            "last_sync": self.get_last_sync_time(),
            "boards": self.get_board_summary(),
            "clients": self.get_client_count(),
            "castmagic": self.get_castmagic_count()
        }

    # --- Client Profiles ---

    def add_client(self, name: str, business_type: str = "", target_audience: str = "",
                   key_offerings: str = "", notes: str = "") -> bool:
        """Add a new client profile."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO clients (name, business_type, target_audience, key_offerings, notes)
                    VALUES (?, ?, ?, ?, ?)
                """, (name, business_type, target_audience, key_offerings, notes))
            return True
        except sqlite3.IntegrityError:
            return False  # Client already exists

    def update_client(self, name: str, business_type: str = "", target_audience: str = "",
                      key_offerings: str = "", notes: str = ""):
        """Update an existing client profile."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE clients
                SET business_type = ?, target_audience = ?, key_offerings = ?, notes = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE name = ?
            """, (business_type, target_audience, key_offerings, notes, name))

    def get_client(self, name: str) -> Optional[dict]:
        """Get a client profile by name."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM clients WHERE name = ?", (name,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_clients(self) -> list[dict]:
        """Get all client profiles."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM clients ORDER BY name")
            return [dict(row) for row in cursor.fetchall()]

    def delete_client(self, name: str):
        """Delete a client profile."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM clients WHERE name = ?", (name,))

    def get_client_count(self) -> int:
        """Get the total number of clients."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM clients")
            return cursor.fetchone()["count"]

    def get_client_context(self) -> str:
        """Get all client info as context string."""
        clients = self.get_all_clients()
        if not clients:
            return ""

        parts = ["=== CLIENT PROFILES ==="]
        for client in clients:
            parts.append(f"\n--- Client: {client['name']} ---")
            if client.get('business_type'):
                parts.append(f"Business: {client['business_type']}")
            if client.get('target_audience'):
                parts.append(f"Target Audience: {client['target_audience']}")
            if client.get('key_offerings'):
                parts.append(f"Key Offerings: {client['key_offerings']}")
            if client.get('notes'):
                parts.append(f"Notes: {client['notes']}")

        return "\n".join(parts)

    # --- Cast Magic Transcripts ---

    def upsert_castmagic_transcript(
        self,
        transcript_id: str,
        title: Optional[str],
        source_url: str,
        status: str,
        duration_seconds: Optional[float],
        language: Optional[str],
        transcript_text: Optional[str],
        content_text: str
    ):
        """Insert or update a Cast Magic transcript."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO castmagic_transcripts
                (id, title, source_url, status, duration_seconds, language,
                 transcript_text, content_text, synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                transcript_id, title, source_url, status, duration_seconds,
                language, transcript_text, content_text
            ))

    def get_castmagic_transcript(self, transcript_id: str) -> Optional[dict]:
        """Get a Cast Magic transcript by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM castmagic_transcripts WHERE id = ?", (transcript_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_castmagic_content(self) -> str:
        """Get all Cast Magic transcript content as a combined text string."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT content_text FROM castmagic_transcripts WHERE status = 'completed' ORDER BY synced_at")
            rows = cursor.fetchall()
            return "\n\n".join(row["content_text"] for row in rows if row["content_text"])

    def get_castmagic_transcripts(self) -> list[dict]:
        """Get all Cast Magic transcripts."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM castmagic_transcripts ORDER BY synced_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    def get_castmagic_count(self) -> int:
        """Get the total number of Cast Magic transcripts."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM castmagic_transcripts")
            return cursor.fetchone()["count"]

    def delete_castmagic_transcript(self, transcript_id: str):
        """Delete a Cast Magic transcript."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM castmagic_transcripts WHERE id = ?", (transcript_id,))

    def clear_castmagic_transcripts(self):
        """Delete all Cast Magic transcripts."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM castmagic_transcripts")

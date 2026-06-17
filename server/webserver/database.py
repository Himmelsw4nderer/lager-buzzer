"""
SQLite Database Module for Buzzer Persistence

This module provides database operations for storing and retrieving buzzer data
(name, color, enabled status) to ensure consistency across Gunicorn workers.
"""

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Database configuration
# Default path is relative to the webserver directory, but can be overridden
# In Docker, use /app/data/buzzers.db for persistence
DB_NAME = os.getenv("BUZZER_DB_PATH", "buzzers.db")


def get_db_path() -> Path:
    """Get the database path, creating parent directories if needed."""
    db_path = Path(DB_NAME)
    if not db_path.is_absolute():
        # Make it relative to the webserver directory
        db_path = Path(__file__).parent / DB_NAME
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def init_db():
    """Initialize the database with required tables."""
    db_path = get_db_path()
    logger.info(f"Initializing database at {db_path}")

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()

        # Create buzzers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS buzzers (
                client_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                color TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                ip_address TEXT,
                buzz_count INTEGER NOT NULL DEFAULT 0,
                last_buzz_time REAL,
                created_at REAL NOT NULL DEFAULT (strftime('%s', 'now')),
                updated_at REAL NOT NULL DEFAULT (strftime('%s', 'now'))
            )
        """)

        # Create index for faster lookups
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_buzzers_client_id ON buzzers(client_id)"
        )

        conn.commit()
        logger.info("Database tables created successfully")
    finally:
        conn.close()


def get_buzzer(db_path: Path, client_id: str) -> Optional[Dict[str, Any]]:
    """Get a single buzzer by client_id from the database."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM buzzers WHERE client_id = ?", (client_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


def get_all_buzzers(db_path: Path) -> Dict[str, Dict[str, Any]]:
    """Get all buzzers from the database as a dictionary keyed by client_id."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM buzzers ORDER BY client_id")
        rows = cursor.fetchall()
        return {row["client_id"]: dict(row) for row in rows}
    finally:
        conn.close()


def save_buzzer(
    db_path: Path,
    client_id: str,
    name: str,
    color: Optional[str] = None,
    enabled: bool = True,
    ip_address: Optional[str] = None,
    buzz_count: int = 0,
    last_buzz_time: Optional[float] = None,
) -> bool:
    """Save or update a buzzer in the database."""
    import time

    now = time.time()

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()

        # Check if buzzer exists
        existing = get_buzzer(db_path, client_id)

        if existing:
            # Update existing buzzer
            cursor.execute(
                """
                UPDATE buzzers
                SET name = ?, color = ?, enabled = ?, ip_address = ?,
                    buzz_count = ?, last_buzz_time = ?, updated_at = ?
                WHERE client_id = ?
            """,
                (
                    name,
                    color,
                    1 if enabled else 0,
                    ip_address,
                    buzz_count,
                    last_buzz_time,
                    now,
                    client_id,
                ),
            )
        else:
            # Insert new buzzer
            cursor.execute(
                """
                INSERT INTO buzzers (client_id, name, color, enabled, ip_address, buzz_count, last_buzz_time)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    client_id,
                    name,
                    color,
                    1 if enabled else 0,
                    ip_address,
                    buzz_count,
                    last_buzz_time,
                ),
            )

        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error saving buzzer {client_id}: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def delete_buzzer(db_path: Path, client_id: str) -> bool:
    """Delete a buzzer from the database."""
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM buzzers WHERE client_id = ?", (client_id,))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Error deleting buzzer {client_id}: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def update_buzzer_field(db_path: Path, client_id: str, field: str, value: Any) -> bool:
    """Update a specific field for a buzzer."""
    import time

    now = time.time()

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE buzzers SET {field} = ?, updated_at = ? WHERE client_id = ?",
            (value, now, client_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Error updating buzzer {client_id} field {field}: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

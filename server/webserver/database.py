"""
Database module for LagerBuzzer
Persists buzzer data (names, colors, enabled state) to SQLite database
so that all workers/clients see the same data.
"""

import os
import sqlite3
import threading
from typing import Any, Dict, Optional

# Default database path - use /app/data in Docker, /tmp otherwise
DEFAULT_DB_DIR = "/app/data" if os.path.exists("/app/data") else "/tmp"
DATABASE_PATH = os.getenv(
    "BUZZER_DB_PATH", os.path.join(DEFAULT_DB_DIR, "lagerbuzzer.db")
)

# Ensure directory exists
os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)

# Lock for thread-safe database operations
_db_lock = threading.Lock()


def init_db():
    """Initialize the database and create tables if they don't exist."""
    with _db_lock:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        cursor = conn.cursor()

        # Create buzzers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS buzzers (
                client_id TEXT PRIMARY KEY,
                ip_address TEXT,
                name TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                buzz_count INTEGER NOT NULL DEFAULT 0,
                color TEXT,
                last_buzz_time REAL
            )
        """)

        conn.commit()
        conn.close()


def get_buzzer(client_id: str) -> Optional[Dict[str, Any]]:
    """Get a buzzer from the database. Returns None if not found."""
    with _db_lock:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM buzzers WHERE client_id = ?", (client_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return dict(row)
        return None


def get_all_buzzers() -> Dict[str, Dict[str, Any]]:
    """Get all buzzers from the database. Returns dict of client_id -> buzzer data."""
    with _db_lock:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM buzzers")
        rows = cursor.fetchall()
        conn.close()

        return {row["client_id"]: dict(row) for row in rows}


def save_buzzer(
    client_id: str,
    ip_address: Optional[str] = None,
    name: Optional[str] = None,
    enabled: Optional[bool] = None,
    buzz_count: Optional[int] = None,
    color: Optional[str] = None,
    last_buzz_time: Optional[float] = None,
) -> bool:
    """
    Save or update a buzzer in the database.
    Only updates the fields that are provided (not None).
    Returns True if the buzzer was inserted, False if it was updated.
    """
    with _db_lock:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        cursor = conn.cursor()

        # Check if buzzer exists
        cursor.execute(
            "SELECT client_id FROM buzzers WHERE client_id = ?", (client_id,)
        )
        exists = cursor.fetchone() is not None

        if exists:
            # Update existing buzzer
            updates = []
            params = []

            if ip_address is not None:
                updates.append("ip_address = ?")
                params.append(ip_address)
            if name is not None:
                updates.append("name = ?")
                params.append(name)
            if enabled is not None:
                updates.append("enabled = ?")
                params.append(1 if enabled else 0)
            if buzz_count is not None:
                updates.append("buzz_count = ?")
                params.append(buzz_count)
            if color is not None:
                updates.append("color = ?")
                params.append(color)
            if last_buzz_time is not None:
                updates.append("last_buzz_time = ?")
                params.append(last_buzz_time)

            if updates:
                params.append(client_id)
                query = f"UPDATE buzzers SET {', '.join(updates)} WHERE client_id = ?"
                cursor.execute(query, params)
                conn.commit()
        else:
            # Insert new buzzer
            cursor.execute(
                """INSERT INTO buzzers (client_id, ip_address, name, enabled, buzz_count, color, last_buzz_time)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (client_id, ip_address, name or client_id, 1, 0, color, last_buzz_time),
            )
            conn.commit()

        conn.close()
        return not exists


def delete_buzzer(client_id: str) -> bool:
    """Delete a buzzer from the database. Returns True if deleted, False if not found."""
    with _db_lock:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM buzzers WHERE client_id = ?", (client_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return deleted


def clear_all_buzzers() -> int:
    """Clear all buzzers from the database. Returns number of buzzers deleted."""
    with _db_lock:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM buzzers")
        count = cursor.rowcount
        conn.commit()
        conn.close()
        return count

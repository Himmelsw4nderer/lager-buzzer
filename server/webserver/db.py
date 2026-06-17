#!/usr/bin/env python3
"""
SQLite Database Module for LagerBuzzer
Handles persistent storage of buzzer data (name, color, enabled status)
to ensure consistency across Gunicorn workers.
"""

import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Optional, Dict, Any

# Database configuration
DB_PATH = os.getenv("BUZZER_DB_PATH", "buzzers.db")

# Thread-local storage for database connections
_thread_local = threading.local()


def get_db_path():
    """Get the database path, creating directory if needed."""
    db_path = DB_PATH
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)
    return db_path


def get_connection():
    """Get a thread-local database connection."""
    if not hasattr(_thread_local, 'conn'):
        db_path = get_db_path()
        _thread_local.conn = sqlite3.connect(
            db_path,
            check_same_thread=False,
            isolation_level=None  # Auto-commit mode
        )
        _thread_local.conn.row_factory = sqlite3.Row
    return _thread_local.conn


@contextmanager
def get_db_cursor():
    """Context manager for database cursor with automatic cleanup."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        yield cursor
    finally:
        cursor.close()


def init_db():
    """Initialize the database schema."""
    with get_db_cursor() as cursor:
        # Create buzzers table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS buzzers (
                client_id TEXT PRIMARY KEY,
                ip_address TEXT,
                name TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                buzz_count INTEGER NOT NULL DEFAULT 0,
                color TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create index on client_id for fast lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_buzzers_client_id 
            ON buzzers (client_id)
        """)
        
        # Create rounds table for future use
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                winner_id TEXT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ended_at TIMESTAMP,
                FOREIGN KEY (winner_id) REFERENCES buzzers (client_id)
            )
        """)


def close_db():
    """Close the database connection for the current thread."""
    if hasattr(_thread_local, 'conn'):
        _thread_local.conn.close()
        del _thread_local.conn


# ============================================================================
# Buzzer CRUD Operations
# ============================================================================

def get_buzzer(client_id: str) -> Optional[Dict[str, Any]]:
    """Get a buzzer by client_id from the database."""
    with get_db_cursor() as cursor:
        cursor.execute(
            "SELECT * FROM buzzers WHERE client_id = ?",
            (client_id,)
        )
        row = cursor.fetchone()
        if row:
            return {
                "client_id": row["client_id"],
                "ip_address": row["ip_address"],
                "name": row["name"],
                "enabled": bool(row["enabled"]),
                "buzz_count": row["buzz_count"],
                "color": row["color"],
            }
        return None


def get_all_buzzers() -> Dict[str, Dict[str, Any]]:
    """Get all buzzers from the database."""
    buzzers = {}
    with get_db_cursor() as cursor:
        cursor.execute("SELECT * FROM buzzers")
        rows = cursor.fetchall()
        for row in rows:
            buzzers[row["client_id"]] = {
                "client_id": row["client_id"],
                "ip_address": row["ip_address"],
                "name": row["name"],
                "enabled": bool(row["enabled"]),
                "buzz_count": row["buzz_count"],
                "color": row["color"],
            }
    return buzzers


def create_or_update_buzzer(client_id: str, ip_address: Optional[str] = None, 
                             name: Optional[str] = None, enabled: bool = True,
                             buzz_count: int = 0, color: Optional[str] = None) -> Dict[str, Any]:
    """Create or update a buzzer in the database using atomic upsert."""
    with get_db_cursor() as cursor:
        # Use INSERT OR IGNORE first, then UPDATE
        # This is atomic and handles race conditions between workers
        cursor.execute(
            """INSERT OR IGNORE INTO buzzers (client_id, ip_address, name, enabled, buzz_count, color)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (client_id, ip_address, name or client_id, int(enabled), buzz_count, color)
        )
        
        # Now update any fields that were provided
        update_fields = []
        params = []
        
        if ip_address is not None:
            update_fields.append("ip_address = ?")
            params.append(ip_address)
        
        if name is not None:
            update_fields.append("name = ?")
            params.append(name)
        
        update_fields.append("enabled = ?")
        params.append(int(enabled))
        
        update_fields.append("buzz_count = ?")
        params.append(buzz_count)
        
        if color is not None:
            update_fields.append("color = ?")
            params.append(color)
        
        update_fields.append("updated_at = CURRENT_TIMESTAMP")
        params.append(client_id)
        
        cursor.execute(
            f"UPDATE buzzers SET {', '.join(update_fields)} WHERE client_id = ?",
            params
        )
        
        # Return the buzzer
        return get_buzzer(client_id)


def update_buzzer_field(client_id: str, field: str, value) -> bool:
    """Update a specific field of a buzzer."""
    valid_fields = {"name", "enabled", "buzz_count", "color", "ip_address"}
    if field not in valid_fields:
        return False
    
    with get_db_cursor() as cursor:
        if field == "enabled":
            cursor.execute(
                f"UPDATE buzzers SET {field} = ?, updated_at = CURRENT_TIMESTAMP WHERE client_id = ?",
                (int(value), client_id)
            )
        else:
            cursor.execute(
                f"UPDATE buzzers SET {field} = ?, updated_at = CURRENT_TIMESTAMP WHERE client_id = ?",
                (value, client_id)
            )
        return cursor.rowcount > 0


def delete_buzzer(client_id: str) -> bool:
    """Delete a buzzer from the database."""
    with get_db_cursor() as cursor:
        cursor.execute("DELETE FROM buzzers WHERE client_id = ?", (client_id,))
        return cursor.rowcount > 0


def delete_all_buzzers() -> int:
    """Delete all buzzers from the database."""
    with get_db_cursor() as cursor:
        cursor.execute("DELETE FROM buzzers")
        return cursor.rowcount


def increment_buzz_count(client_id: str) -> bool:
    """Increment the buzz count for a buzzer."""
    with get_db_cursor() as cursor:
        cursor.execute(
            "UPDATE buzzers SET buzz_count = buzz_count + 1, updated_at = CURRENT_TIMESTAMP WHERE client_id = ?",
            (client_id,)
        )
        return cursor.rowcount > 0


# ============================================================================
# Initialization
# ============================================================================

# Initialize database when module is imported
init_db()

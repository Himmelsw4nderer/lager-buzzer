#!/usr/bin/env python3
"""
SQLite Database Module for LagerBuzzer
Persists buzzer names and colors across Gunicorn workers
"""

import logging
import os
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

# Database path - default to data directory in webserver folder
DB_DIR = Path(__file__).parent / "data"
DB_PATH = DB_DIR / "lagerbuzzer.db"


def get_db_path():
    """Get the database path, creating data directory if needed."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    return str(DB_PATH)


def init_db():
    """Initialize the database and create tables if they don't exist."""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create buzzers table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS buzzers (
            client_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            color TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create index for faster lookups
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_buzzers_client_id ON buzzers(client_id)
    """)

    conn.commit()
    conn.close()
    logger.info(f"Database initialized at {db_path}")


def get_connection():
    """Get a database connection."""
    return sqlite3.connect(get_db_path())


def get_buzzer(client_id):
    """Get a buzzer by client_id from the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT client_id, name, color FROM buzzers WHERE client_id = ?", (client_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if row:
        return {"client_id": row[0], "name": row[1], "color": row[2]}
    return None


def get_all_buzzers():
    """Get all buzzers from the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT client_id, name, color FROM buzzers ORDER BY name")
    rows = cursor.fetchall()
    conn.close()

    buzzers = {}
    for row in rows:
        buzzers[row[0]] = {"client_id": row[0], "name": row[1], "color": row[2]}
    return buzzers


def save_buzzer(client_id, name, color=None):
    """Save or update a buzzer in the database."""
    conn = get_connection()
    cursor = conn.cursor()

    # Check if buzzer exists
    cursor.execute("SELECT 1 FROM buzzers WHERE client_id = ?", (client_id,))
    exists = cursor.fetchone() is not None

    if exists:
        # Update existing buzzer
        cursor.execute(
            """
            UPDATE buzzers
            SET name = ?, color = ?, updated_at = CURRENT_TIMESTAMP
            WHERE client_id = ?
        """,
            (name, color, client_id),
        )
        logger.debug(f"Updated buzzer {client_id} in database")
    else:
        # Insert new buzzer
        cursor.execute(
            """
            INSERT INTO buzzers (client_id, name, color)
            VALUES (?, ?, ?)
        """,
            (client_id, name, color),
        )
        logger.debug(f"Saved new buzzer {client_id} to database")

    conn.commit()
    conn.close()


def delete_buzzer(client_id):
    """Delete a buzzer from the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM buzzers WHERE client_id = ?", (client_id,))
    conn.commit()
    conn.close()
    logger.debug(f"Deleted buzzer {client_id} from database")


def delete_all_buzzers():
    """Delete all buzzers from the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM buzzers")
    conn.commit()
    conn.close()
    logger.info("Deleted all buzzers from database")

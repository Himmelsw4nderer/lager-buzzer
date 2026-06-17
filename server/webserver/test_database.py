#!/usr/bin/env python3
"""
Test script for the SQLite database module.
Run this to verify the database operations work correctly.
"""

import os
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import (
    delete_buzzer,
    get_all_buzzers,
    get_buzzer,
    get_db_path,
    init_db,
    save_buzzer,
)


def main():
    # Use a test database file
    test_db = Path("/tmp/test_buzzers.db")
    if test_db.exists():
        os.remove(str(test_db))

    # Monkey patch to use test database
    import database

    original_get_db_path = database.get_db_path
    database.get_db_path = lambda: test_db

    try:
        # Initialize database
        init_db()
        print("✓ Database initialized")

        # Test saving a buzzer
        save_buzzer(
            db_path=test_db,
            client_id="buzzer1",
            name="Test Buzzer 1",
            color="#FF0000",
            enabled=True,
            ip_address="192.168.1.1",
            buzz_count=5,
            last_buzz_time=None,
        )
        print("✓ Saved buzzer1")

        # Test saving another buzzer
        save_buzzer(
            db_path=test_db,
            client_id="buzzer2",
            name="Test Buzzer 2",
            color="#00FF00",
            enabled=False,
            ip_address="192.168.1.2",
            buzz_count=10,
        )
        print("✓ Saved buzzer2")

        # Test getting a single buzzer
        buzzer1 = get_buzzer(test_db, "buzzer1")
        assert buzzer1 is not None, "buzzer1 should exist"
        assert buzzer1["name"] == "Test Buzzer 1", (
            f"Expected 'Test Buzzer 1', got {buzzer1['name']}"
        )
        assert buzzer1["color"] == "#FF0000", (
            f"Expected '#FF0000', got {buzzer1['color']}"
        )
        assert buzzer1["enabled"] == 1, f"Expected enabled=1, got {buzzer1['enabled']}"
        print("✓ Retrieved buzzer1 correctly")

        # Test getting all buzzers
        all_buzzers = get_all_buzzers(test_db)
        assert len(all_buzzers) == 2, f"Expected 2 buzzers, got {len(all_buzzers)}"
        print("✓ Retrieved all buzzers correctly")

        # Test updating a buzzer
        save_buzzer(
            db_path=test_db,
            client_id="buzzer1",
            name="Updated Buzzer 1",
            color="#FF0000",
            enabled=True,
            ip_address="192.168.1.1",
            buzz_count=6,
        )
        buzzer1_updated = get_buzzer(test_db, "buzzer1")
        assert buzzer1_updated["name"] == "Updated Buzzer 1", "Name should be updated"
        assert buzzer1_updated["buzz_count"] == 6, "Buzz count should be updated"
        print("✓ Updated buzzer1 correctly")

        # Test deleting a buzzer
        delete_buzzer(test_db, "buzzer2")
        all_buzzers = get_all_buzzers(test_db)
        assert len(all_buzzers) == 1, (
            f"Expected 1 buzzer after deletion, got {len(all_buzzers)}"
        )
        print("✓ Deleted buzzer2 correctly")

        print("\n✅ All database tests passed!")
        return 0

    finally:
        # Clean up
        if test_db.exists():
            os.remove(str(test_db))
        database.get_db_path = original_get_db_path


if __name__ == "__main__":
    sys.exit(main())

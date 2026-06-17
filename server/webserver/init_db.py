#!/usr/bin/env python3
"""
Database initialization script for LagerBuzzer
This script initializes the SQLite database and can be run independently.
"""

import os
import sys

# Add the current directory to the path so we can import db module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import get_db_path, init_db

if __name__ == "__main__":
    print("Initializing LagerBuzzer database...")
    db_path = get_db_path()
    print(f"Database path: {db_path}")

    init_db()
    print(f"✓ Database initialized successfully at {db_path}")

    # Verify the database was created
    if os.path.exists(db_path):
        file_size = os.path.getsize(db_path)
        print(f"✓ Database file exists (size: {file_size} bytes)")
    else:
        print("✗ Database file was not created")
        sys.exit(1)

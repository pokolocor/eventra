#!/usr/bin/env python3
"""Initialize the database schema by creating all tables."""

import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from backend.database.orm import Base
    from backend.database.session import create_engine_for
    from backend.config import load_settings

    # Load settings
    settings = load_settings()

    if not settings.database_url:
        print("ERROR: DATABASE_URL is not set")
        print("\nPlease set DATABASE_URL environment variable:")
        print("  Windows PowerShell: $env:DATABASE_URL='your_database_url'")
        print("  Linux/Mac: export DATABASE_URL='your_database_url'")
        sys.exit(1)

    print(f"Connecting to database...")
    print(f"URL: {settings.database_url[:50]}...")

    # Create engine
    engine = create_engine_for(settings)

    # Create all tables
    print("\nCreating tables...")
    Base.metadata.create_all(engine)

    # Verify tables were created
    from sqlalchemy import inspect

    inspector = inspect(engine)
    tables = inspector.get_table_names()

    print(f"\n✓ Successfully created {len(tables)} tables:")
    for table in sorted(tables):
        print(f"  - {table}")

    print("\n✓ Database schema initialized successfully!")
    print("\nYou can now run the export script:")
    print("  python export_paper_trading_log.py")

except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

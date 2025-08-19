#!/usr/bin/env python
"""Create test database for pytest."""

import asyncio

import asyncpg


async def create_test_database():
    """Create the test database if it doesn't exist."""
    # Connect to the default postgres database
    conn = await asyncpg.connect(
        host="localhost",
        port=5433,  # PostgreSQL is running on port 5433
        user="ozuser",
        password="ozpassword",
        database="oz_monitor",  # Connect to existing DB to create test DB
    )

    try:
        # Check if test database exists
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = 'blip0_test'")

        if not exists:
            # Create the test database
            await conn.execute("CREATE DATABASE blip0_test")
            print("✅ Test database 'blip0_test' created successfully!")
        else:
            print("ℹ️ Test database 'blip0_test' already exists.")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(create_test_database())

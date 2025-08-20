#!/usr/bin/env python
"""Create test database for pytest."""

import asyncio

import asyncpg
from tests.test_config import test_settings


async def create_test_database():
    """Create the test database if it doesn't exist."""
    # Connect to the default postgres database using test settings
    conn = await asyncpg.connect(
        host=test_settings.TEST_POSTGRES_SERVER,
        port=test_settings.TEST_POSTGRES_PORT,
        user=test_settings.TEST_POSTGRES_USER,
        password=test_settings.TEST_POSTGRES_PASSWORD,
        database="postgres",  # Connect to default postgres DB to create test DB
    )

    try:
        # Check if test database exists
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", test_settings.TEST_POSTGRES_DB
        )

        if not exists:
            # Create the test database
            await conn.execute(f"CREATE DATABASE {test_settings.TEST_POSTGRES_DB}")
            print(f"✅ Test database '{test_settings.TEST_POSTGRES_DB}' created successfully!")
        else:
            print(f"ℹ️ Test database '{test_settings.TEST_POSTGRES_DB}' already exists.")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(create_test_database())

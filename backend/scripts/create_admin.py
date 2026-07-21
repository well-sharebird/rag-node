#!/usr/bin/env python
"""
Create default admin user manually
Usage: uv run python scripts/create_admin.py

Note: This uses the database config from backend/.env
"""
import asyncio
import sys
sys.path.insert(0, '.')

from app.core.database import async_session_factory
from app.core.init_data import create_admin_user
from app.models.user import Role
from sqlalchemy import select


async def main():
    print("Creating default admin user...")
    print("Using database config from backend/.env")

    try:
        async with async_session_factory() as session:
            # First ensure Admin role exists
            result = await session.execute(select(Role).where(Role.name == "Admin"))
            admin_role = result.scalar_one_or_none()

            if not admin_role:
                print("Admin role not found. Creating roles first...")
                from app.core.init_data import init_roles_and_permissions
                await init_roles_and_permissions(session)

            # Create or update admin user
            admin = await create_admin_user(
                session,
                email="admin@example.com",
                username="admin",
                password="admin123",
                full_name="System Administrator"
            )

            print("\n✓ Admin user ready!")
            print("\nLogin credentials:")
            print("  Username: admin")
            print("  Password: admin123")
            print("\nFrontend: http://localhost:3000 (or your configured URL)")
            print("API Login: curl -X POST http://localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' -d '{\"username\":\"admin\",\"password\":\"admin123\"}'")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        print("\nMake sure the database is running and accessible.")
        print("Check backend/.env for database configuration.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

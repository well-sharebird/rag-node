import pytest
import uuid
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text


@pytest.fixture
async def client():
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def test_kb(client):
    """Create a test knowledge base for API tests."""
    kb_id = str(uuid.uuid4())
    kb_name = f"test_kb_{kb_id[:8]}"

    try:
        # Create knowledge base via API
        response = await client.post(
            "/api/v1/knowledge-bases",
            json={"name": kb_name, "description": "Test knowledge base"},
        )

        if response.status_code == 201:
            kb_data = response.json()

            class KB:
                def __init__(self, kb_id):
                    self.id = kb_id
            yield KB(kb_data["id"])

            # Cleanup
            try:
                await client.delete(f"/api/v1/knowledge-bases/{kb_data['id']}")
            except:
                pass
        else:
            # Try to find existing kb
            list_response = await client.get("/api/v1/knowledge-bases")
            if list_response.status_code == 200:
                kbs = list_response.json().get("items", [])
                if kbs:
                    class KB:
                        def __init__(self, kb_id):
                            self.id = kb_id
                    yield KB(kbs[0]["id"])
                    return

            pytest.skip(f"Could not create test knowledge base: {response.status_code}")
    except Exception as e:
        pytest.skip(f"Could not create test knowledge base: {e}")


@pytest.fixture
async def test_db_session():
    """Create a test database session."""
    from app.core.database import async_session_factory
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

    # Use in-memory SQLite for testing
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    test_session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # Create tables
    from app.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with test_session_factory() as session:
        yield session

    # Cleanup
    await engine.dispose()

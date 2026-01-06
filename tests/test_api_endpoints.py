"""
API Endpoint Tests - Basic endpoint availability tests
"""
import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_endpoint(client):
    """Test health check endpoint."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_root_endpoint(client):
    """Test root endpoint."""
    response = await client.get("/")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_openapi_schema(client):
    """Test OpenAPI schema is available."""
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert "paths" in data
    assert "components" in data


@pytest.mark.asyncio
async def test_docs_endpoint(client):
    """Test Swagger docs endpoint."""
    response = await client.get("/docs")
    assert response.status_code == 200


# === Auth endpoints (require authentication) ===

@pytest.mark.asyncio
async def test_auth_me_requires_auth(client):
    """Test /auth/me requires authentication."""
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


# === Consent endpoints ===

@pytest.mark.asyncio
async def test_consents_requires_auth(client):
    """Test /consents requires authentication."""
    response = await client.get("/api/v1/consents")
    assert response.status_code == 401


# === Energy endpoints ===

@pytest.mark.asyncio
async def test_recommendations_requires_auth(client):
    """Test /energy/recommendations requires authentication."""
    response = await client.get("/api/v1/energy/recommendations?asset_id=00000000-0000-0000-0000-000000000000")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_rewards_balance_requires_auth(client):
    """Test /rewards/balance requires authentication."""
    response = await client.get("/api/v1/rewards/balance")
    assert response.status_code == 401


# === Maintenance endpoints ===

@pytest.mark.asyncio
async def test_alarms_requires_auth(client):
    """Test /maintenance/alarms requires authentication."""
    response = await client.get("/api/v1/maintenance/alarms?asset_id=00000000-0000-0000-0000-000000000000")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_jobs_requires_auth(client):
    """Test /maintenance/jobs requires authentication."""
    response = await client.get("/api/v1/maintenance/jobs")
    assert response.status_code == 401


# === Real Estate endpoints ===

@pytest.mark.asyncio
async def test_assets_requires_auth(client):
    """Test /real-estate/assets requires authentication."""
    response = await client.get("/api/v1/real-estate/assets")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_leases_requires_auth(client):
    """Test /real-estate/leases requires authentication."""
    response = await client.get("/api/v1/real-estate/leases")
    assert response.status_code == 401

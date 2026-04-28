"""API integration tests."""

import pytest
from httpx import AsyncClient
from fastapi import status

from ist.api.main import create_app


@pytest.fixture
def app():
    """Create test app."""
    return create_app()


@pytest.fixture
async def client(app):
    """Create test client."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
class TestHealthEndpoints:
    """Test health check endpoints."""
    
    async def test_health_check(self, client) -> None:
        """Test health endpoint returns 200."""
        response = await client.get("/health")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["data"]["status"] == "healthy"
    
    async def test_version_endpoint(self, client) -> None:
        """Test version endpoint."""
        response = await client.get("/version")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "version" in data["data"]


@pytest.mark.asyncio
class TestStrategyEndpoints:
    """Test strategy management endpoints."""
    
    async def test_create_strategy(self, client) -> None:
        """Test strategy creation."""
        payload = {
            "name": "Test Strategy",
            "description": "Test description",
            "profile_name": "Test Profile",
            "asset_allocation": {
                "forex_majors": 0.5,
                "index_cfds": 0.5
            },
            "nodes": [
                {"id": "node1", "type": "DataSourceNode", "params": {}}
            ],
            "connections": []
        }
        
        response = await client.post("/strategies", json=payload)
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["success"] is True
        assert "id" in data["data"]
    
    async def test_list_strategies(self, client) -> None:
        """Test listing strategies."""
        response = await client.get("/strategies")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)

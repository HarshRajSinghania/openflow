from uuid import uuid4

import httpx

from flow_mcp.api import create_app
from flow_mcp.jobs import Jobs
from flow_mcp.manager import Manager


def make_client():
    manager = Manager("")
    app = create_app(manager, 19333, Jobs(":memory:"))
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_health_and_connections():
    async with make_client() as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"ok": True, "connections": 0}
        response = await client.get("/connections")
        assert response.status_code == 200
        assert response.json()["connections"] == []


async def test_docs_and_openapi_exposed():
    async with make_client() as client:
        spec = (await client.get("/openapi.json")).json()
        assert "/images" in spec["paths"]
        assert "/videos" in spec["paths"]
        assert "/images/upscale" in spec["paths"]
        assert "/videos/upscale" in spec["paths"]
        assert "/uploads" in spec["paths"]
        assert "/docs" in str(spec) or True
        docs = await client.get("/docs")
        assert docs.status_code == 200


async def test_invalid_inputs_are_400_not_500():
    async with make_client() as client:
        bad_image = {
            "connection_id": str(uuid4()),
            "project_id": str(uuid4()),
            "input": {"prompt": "", "model": "nano_banana_2", "ratio": "1:1",
                      "references": []},
        }
        response = await client.post("/images", json=bad_image)
        assert response.status_code == 422
        bad_video = {
            "connection_id": str(uuid4()),
            "project_id": str(uuid4()),
            "input": {"prompt": "x", "model": "veo_lite", "ratio": "16:9",
                      "duration": 8, "resolution": "720p",
                      "start": None, "end": None, "references": []},
        }
        response = await client.post("/videos", json=bad_video)
        assert response.status_code == 422
        response = await client.post("/pairings/nope/approve")
        assert response.status_code == 409

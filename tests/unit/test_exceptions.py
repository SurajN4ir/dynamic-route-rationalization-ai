"""Every error path must normalize to the doc 05 error envelope:
{ "error": { "code", "message", "details" } }. Exercised against a small
isolated app rather than the real one, since Phase 1 has no real endpoint
that raises these errors yet.
"""

from collections.abc import AsyncIterator

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.exceptions import NotFoundError, register_exception_handlers


def _build_test_app() -> FastAPI:
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/boom")
    async def boom() -> None:
        raise NotFoundError("thing missing")

    @test_app.get("/crash")
    async def crash() -> None:
        raise RuntimeError("unexpected failure")

    @test_app.get("/items/{item_id}")
    async def get_item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    return test_app


@pytest_asyncio.fixture
async def error_client() -> AsyncIterator[AsyncClient]:
    # raise_app_exceptions=False: match real server behavior (uvicorn
    # returns the 500 response ServerErrorMiddleware already built instead
    # of re-raising to the caller) so this test observes what a real client
    # would actually receive, not httpx's debugging default.
    transport = ASGITransport(app=_build_test_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


async def test_app_error_returns_structured_envelope(error_client: AsyncClient) -> None:
    response = await error_client.get("/boom")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "thing missing", "details": {}}
    }


async def test_unhandled_exception_returns_generic_500_envelope(
    error_client: AsyncClient,
) -> None:
    response = await error_client.get("/crash")

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    # the raw exception message must never leak to the client
    assert "unexpected failure" not in body["error"]["message"]


async def test_validation_error_returns_structured_envelope(error_client: AsyncClient) -> None:
    response = await error_client.get("/items/not-an-int")

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert "errors" in body["error"]["details"]


async def test_unknown_route_returns_structured_404(error_client: AsyncClient) -> None:
    response = await error_client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_error"

"""Every ``/v1`` route carries the session dependency (PR-27, Task 4d.4, PL-9).

The check walks each route's dependency tree, so a route that reaches the session through
another dependency (``/v1/runs/{run_id}/stream`` through ``visible_run``) counts. Two
guards keep it from passing on routes it cannot see: every entry of ``app.routes`` is an
``APIRoute`` or one of FastAPI's documentation routes (an included router or a mount would
hide its routes from the walk), and the walked ``/v1`` operations equal the OpenAPI
document's. The allow-list holds exactly ``POST /v1/local/session``, the route that
creates the session, and the test asserts it has one entry, so it cannot be widened
quietly (PR-06). Out of its scope, as PR-27's row lists them and the test pins them: the
health probes (the only API routes outside ``/v1``), FastAPI's documentation routes and the
static UI mount (the app is built with one), left to Phase 7.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from e_agent.server import api as api_module
from e_agent.server.api import create_app
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from starlette.routing import Mount, Route

ALLOWED = frozenset({("POST", "/v1/local/session")})
"""Routes without a session: only the one that creates it. Never widen this."""
FASTAPI_DOCS = frozenset({"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"})
"""FastAPI's default documentation routes: outside this test, listed in PR-27's row."""
HEALTH = frozenset({"/health/live", "/health/ready"})
"""The only API routes outside ``/v1``: the operator probes, listed in PR-27's row."""


def _is_v1(path: str) -> bool:
    return path == "/v1" or path.startswith("/v1/")


async def _never() -> Any:  # the route table needs no runtime
    raise RuntimeError


def _calls(dependant: Dependant) -> Iterator[Any]:
    for dependency in dependant.dependencies:
        yield dependency.call
        yield from _calls(dependency)


def _has_session(route: APIRoute) -> bool:
    return any(
        getattr(call, "__name__", None) == "session"
        and getattr(call, "__module__", None) == api_module.__name__
        for call in _calls(route.dependant)
    )


def _static_ui(route: Any) -> bool:
    return isinstance(route, Mount) and route.name == "ui" and isinstance(route.app, StaticFiles)


def test_every_v1_route_has_an_authorization_dependency(tmp_path: Path) -> None:
    app = create_app(_never, static_dir=tmp_path)  # with the static UI mount, as served
    unseen = [
        route
        for route in app.routes
        if not isinstance(route, APIRoute)
        and not (isinstance(route, Route) and route.path in FASTAPI_DOCS)
        and not _static_ui(route)
    ]
    assert unseen == [], "routes the walk cannot see"
    assert [r for r in app.routes if _static_ui(r)] == [app.routes[-1]], "one static mount, last"
    outside = {r.path for r in app.routes if isinstance(r, APIRoute) and not _is_v1(r.path)}
    assert outside == HEALTH, "an API route outside /v1 that this test does not check"
    routes = [
        (method, route.path, route)
        for route in app.routes
        if isinstance(route, APIRoute) and _is_v1(route.path)
        for method in sorted(route.methods)
    ]
    assert len(ALLOWED) == 1
    present = {(method, path) for method, path, _ in routes}
    assert present >= ALLOWED, "an allow-listed route no longer exists"
    documented = {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        if _is_v1(path)
        for method in operations
    }
    assert present == documented
    checked = [(m, p) for m, p, route in routes if (m, p) not in ALLOWED]
    missing = [
        (m, p) for m, p, route in routes if (m, p) not in ALLOWED and not _has_session(route)
    ]
    print(f"checked {len(checked)} /v1 routes for the session dependency")
    assert checked, "no /v1 route was checked"
    assert missing == []
    allowed_route = next(route for m, p, route in routes if (m, p) in ALLOWED)
    assert not _has_session(allowed_route)

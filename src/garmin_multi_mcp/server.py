"""Server bootstrap for the remote multi-account Garmin MCP."""

from __future__ import annotations

from dataclasses import replace
import sys

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
import uvicorn

from garmin_multi_mcp.auth.policy import AuthorizationPolicy
from garmin_multi_mcp.config import load_accounts, load_app_config
from garmin_multi_mcp.garmin_api import GarminClientManager
from garmin_multi_mcp.tools import register_tools


SERVER_INSTRUCTIONS = """
This MCP server exposes Garmin Connect data for multiple pre-configured accounts.
Always call list_accounts first when you are unsure which account_id to use.
Every tool requires an explicit account_id so queries stay scoped to the right person.
Use read tools to inspect profile, wellness, readiness, and activity data for that account.
""".strip()


async def _oauth_disabled_endpoint(_request) -> JSONResponse:
    """OAuth is disabled - return 404 for all OAuth discovery endpoints."""
    return JSONResponse({"error": "OAuth is disabled for this MCP server."}, status_code=404)


def _wrap_trailing_slash_compat(app, request_path: str):
    normalized_path = request_path if request_path.startswith("/") else f"/{request_path}"
    canonical_path = normalized_path.rstrip("/") or "/"
    alternate_path = canonical_path if normalized_path.endswith("/") else f"{canonical_path}/"

    async def wrapped(scope, receive, send):
        if scope["type"] == "http" and scope.get("path") == alternate_path:
            scope = dict(scope)
            scope["path"] = canonical_path
            root_path = scope.get("root_path", "")
            scope["raw_path"] = f"{root_path}{canonical_path}".encode()
        await app(scope, receive, send)

    return wrapped


def _wrap_octet_stream_compat(app, request_path: str):
    normalized_path = request_path if request_path.startswith("/") else f"/{request_path}"
    canonical_path = normalized_path.rstrip("/") or "/"

    async def wrapped(scope, receive, send):
        if scope["type"] == "http" and scope.get("method") == "POST":
            path = scope.get("path", "")
            if path in {canonical_path, f"{canonical_path}/"}:
                raw_headers = scope.get("headers", [])
                rewritten_headers = []
                changed = False
                saw_accept = False
                for key, value in raw_headers:
                    if key.lower() == b"content-type" and value.split(b";", 1)[0].strip() == b"application/octet-stream":
                        rewritten_headers.append((key, b"application/json"))
                        changed = True
                    elif key.lower() == b"accept":
                        saw_accept = True
                        lowered = value.lower()
                        has_json = b"application/json" in lowered
                        has_sse = b"text/event-stream" in lowered
                        has_wildcard = b"*/*" in lowered
                        if has_wildcard or not (has_json and has_sse):
                            rewritten_headers.append((key, b"application/json, text/event-stream"))
                            changed = True
                        else:
                            rewritten_headers.append((key, value))
                    else:
                        rewritten_headers.append((key, value))
                if not saw_accept:
                    rewritten_headers.append((b"accept", b"application/json, text/event-stream"))
                    changed = True
                if changed:
                    scope = dict(scope)
                    scope["headers"] = rewritten_headers
        await app(scope, receive, send)

    return wrapped


def _wrap_http_app(http_app, runtime_config) -> Starlette:
    wrapped_app = _wrap_trailing_slash_compat(http_app, runtime_config.path)
    wrapped_app = _wrap_octet_stream_compat(wrapped_app, runtime_config.path)

    lifespan = getattr(http_app.router, "lifespan_context", None)
    root_app = Starlette(
        lifespan=lifespan,
        routes=[
            Route(
                "/.well-known/oauth-protected-resource",
                _oauth_disabled_endpoint,
                methods=["GET"],
            ),
            Route(
                "/.well-known/oauth-protected-resource/{transport:path}",
                _oauth_disabled_endpoint,
                methods=["GET"],
            ),
            Route(
                "/.well-known/oauth-authorization-server",
                _oauth_disabled_endpoint,
                methods=["GET"],
            ),
            Route("/oauth/authorize", _oauth_disabled_endpoint, methods=["GET"]),
            Mount("", app=wrapped_app),
        ],
    )
    root_app.state.runtime_config = runtime_config
    return root_app


def build_app() -> tuple[FastMCP, GarminClientManager, object]:
    """Build the MCP app and account manager."""

    load_dotenv()
    runtime_config = load_app_config()
    accounts, config_default_account_id, oidc_config = load_accounts(runtime_config.accounts_file)
    runtime_config = replace(runtime_config, oidc=oidc_config)
    manager = GarminClientManager(
        accounts=accounts,
        default_account_id=runtime_config.default_account_id or config_default_account_id,
    )
    authz_policy = AuthorizationPolicy(runtime_config.oidc, sorted(accounts))

    app = FastMCP(
        name="Garmin Multi Account MCP",
        instructions=SERVER_INSTRUCTIONS,
    )
    app.settings.streamable_http_path = runtime_config.path
    app.settings.stateless_http = True
    app.settings.json_response = True
    app.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=runtime_config.allowed_hosts,
        allowed_origins=runtime_config.allowed_origins,
    )
    register_tools(app, manager, runtime_config.oidc, authz_policy)
    return app, manager, runtime_config


def main() -> None:
    """Run the server in stdio or remote HTTP mode."""

    try:
        app, manager, runtime_config = build_app()
    except Exception as err:
        print(f"Server bootstrap failed: {err}", file=sys.stderr)
        raise

    account_count = len(manager.list_accounts())
    print(
        f"Loaded {account_count} Garmin account(s). Transport={runtime_config.transport}",
        file=sys.stderr,
    )

    if runtime_config.transport in {"stdio", "STDIO"}:
        app.run()
        return

    transport = runtime_config.transport.lower()
    if transport in {"http", "streamable-http"}:
        http_app = _wrap_http_app(app.streamable_http_app(), runtime_config)
        uvicorn.run(http_app, host=runtime_config.host, port=runtime_config.port)
        return

    if transport == "sse":
        sse_app = app.sse_app(mount_path=runtime_config.path)
        uvicorn.run(sse_app, host=runtime_config.host, port=runtime_config.port)
        return

    raise ValueError(
        f"Unsupported transport '{runtime_config.transport}'. "
        "Use stdio, http, streamable-http, or sse."
    )


if __name__ == "__main__":
    main()

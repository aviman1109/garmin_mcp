"""Protected resource stub - service_error_result and OAuth metadata responses."""

from __future__ import annotations

from starlette.responses import JSONResponse

from mcp.types import CallToolResult, TextContent


def service_error_result(message: str) -> CallToolResult:
    """Return a stable MCP tool error for backend/service failures."""
    return CallToolResult(
        content=[TextContent(type="text", text=message)],
        isError=True,
    )


def protected_resource_metadata_response(config: object) -> JSONResponse:
    """OAuth disabled - return 404."""
    return JSONResponse({"error": "OAuth is disabled for this MCP server."}, status_code=404)


def authorization_server_metadata_response(config: object) -> JSONResponse:
    """OAuth disabled - return 404."""
    return JSONResponse({"error": "OAuth is disabled for this MCP server."}, status_code=404)

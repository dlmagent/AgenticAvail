from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover - optional dependency guard
    FastMCP = None

from .availability import SearchRequest, search_hotels
from .context import UpsertRequest, get_session_state, upsert_session
from .extraction import ExtractRequest, extract_patch
from .property_resolver import ResolveRequest, resolve_property
from .results_explainer import ExplainRequest, explain_results


MCP_FACADE_AVAILABLE = FastMCP is not None
MCP_FACADE_IMPORT_ERROR = None if MCP_FACADE_AVAILABLE else "Install the optional 'mcp' package to enable the MCP facade."


if MCP_FACADE_AVAILABLE:
    mcp_server = FastMCP(
        "AgenticAvail MCP",
        instructions=(
            "Unified hotel-search MCP facade for session context, extraction, property resolution, "
            "availability search, and grounded result explanation."
        ),
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
    )

    @mcp_server.tool()
    def context_get(session_id: str) -> dict[str, Any]:
        """Retrieve the current session state for a session ID."""
        return get_session_state(session_id).model_dump(mode="json")


    @mcp_server.tool()
    def context_upsert(session_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Update session state with a partial patch and return the new state."""
        return upsert_session(UpsertRequest(session_id=session_id, patch=patch)).model_dump(mode="json")


    @mcp_server.tool()
    def extraction_parse(session_id: str, user_message: str, state: dict[str, Any]) -> dict[str, Any]:
        """Extract hotel-search intent and state updates from a natural-language user message."""
        return extract_patch(
            ExtractRequest(session_id=session_id, user_message=user_message, state=state)
        ).model_dump(mode="json")


    @mcp_server.tool()
    def property_resolve(query: str, city: str, state=None, radius_miles=None) -> dict[str, Any]:
        """Resolve a place or POI to coordinates and nearby candidate hotels."""
        return resolve_property(
            ResolveRequest(query=query, city=city, state=state or "GA", radius_miles=radius_miles)
        ).model_dump(mode="json")


    @mcp_server.tool()
    def availability_search(
        city: str,
        check_in: str,
        check_out: str,
        rooms: int = 1,
        guests: int = 2,
        state=None,
        neighborhood=None,
        required_amenities=None,
        preferred_amenities=None,
        max_nightly_rate_usd=None,
        max_total_usd=None,
        poi_lat=None,
        poi_lng=None,
        sort_by=None,
    ) -> dict[str, Any]:
        """Search hotel availability, pricing, and amenities for a stay window."""
        request = SearchRequest(
            city=city,
            state=state,
            check_in=check_in,
            check_out=check_out,
            rooms=rooms,
            guests=guests,
            neighborhood=neighborhood,
            required_amenities=required_amenities,
            preferred_amenities=preferred_amenities,
            max_nightly_rate_usd=max_nightly_rate_usd,
            max_total_usd=max_total_usd,
            poi_lat=poi_lat,
            poi_lng=poi_lng,
            sort_by=sort_by,
        )
        return search_hotels(request).model_dump(mode="json")


    @mcp_server.tool()
    def results_explain(session_id: str, user_message: str, state: dict[str, Any], search_response: dict[str, Any]) -> dict[str, Any]:
        """Explain availability-search results in grounded natural language."""
        return explain_results(
            ExplainRequest(
                session_id=session_id,
                user_message=user_message,
                state=state,
                search_response=search_response,
            )
        ).model_dump(mode="json")


    mcp_http_app = mcp_server.streamable_http_app()
else:  # pragma: no cover - optional dependency guard
    mcp_server = None
    mcp_http_app = None

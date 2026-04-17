from __future__ import annotations

import json
import os
import uuid
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from dateutil.parser import parse as dtparse
from openai import OpenAI
from pydantic import BaseModel, Field

from .mcp import LocalMCPClient


MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1")
CONVERSATIONS: Dict[str, List[dict]] = {}
REACT_SYSTEM_PROMPT = """You are a hotel search assistant with access to tools for finding hotels.

Available tools:
- context_get: Retrieve session state (args: session_id)
- context_upsert: Update session state (args: session_id, patch)
- extraction_parse: Extract search parameters from user message (args: session_id, user_message, state)
- property_resolve: Resolve location/POI to coordinates (args: query, city, state, radius_miles)
- availability_search: Search for available hotels (args: city, state, check_in, check_out, rooms, guests, neighborhood, required_amenities, preferred_amenities, max_nightly_rate_usd, max_total_usd, poi_lat, poi_lng, sort_by)
- results_explain: Generate natural language explanation of search results (args: session_id, user_message, state, search_response)

IMPORTANT:
1. Always start by calling context_get to retrieve current session state
2. Use extraction_parse to understand what the user wants
3. When the user asks to search or check availability, call availability_search only after the user has provided a destination and dates
4. If the user asks for the closest or nearest matching hotel to a place, call property_resolve first and then call availability_search with sort_by=closest_to_poi plus the resolved poi_lat/poi_lng
5. Always call results_explain after availability_search to format results
6. Demo supports ONLY Atlanta, GA and June 2026
7. NEVER invent hotel data - only use tool results
8. Use defaults only for rooms=1 and guests=2. Do not assume a destination or dates.
9. Do NOT ask for rooms/guests unless user specifically mentions needing multiple rooms or a large group

Call tools directly using their exact names (e.g., context_get, not functions.context_get).
"""


class ChatRequest(BaseModel):
    session_id: str = Field(..., examples=["demo-1"])
    message: str = Field(..., examples=["Must have a pool. Prefer spa. Cheapest total June 10-13 2026."])


class ChatResponse(BaseModel):
    session_id: str
    assistant_message: str
    trace: list


def _preview(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict) and "capability" in obj and "ok" in obj:
        inner = obj.get("result")
        if isinstance(inner, dict) and "matches" in inner and isinstance(inner["matches"], list):
            return {
                "capability": obj.get("capability"),
                "ok": obj.get("ok"),
                "status_code": obj.get("status_code"),
                "elapsed_ms": obj.get("elapsed_ms"),
                "matches": len(inner["matches"]),
            }
        if isinstance(inner, dict) and "narrative" in inner:
            return {
                "capability": obj.get("capability"),
                "ok": obj.get("ok"),
                "status_code": obj.get("status_code"),
                "elapsed_ms": obj.get("elapsed_ms"),
                "narrative": (inner.get("narrative") or "")[:120],
            }
        return {
            "capability": obj.get("capability"),
            "ok": obj.get("ok"),
            "status_code": obj.get("status_code"),
            "elapsed_ms": obj.get("elapsed_ms"),
            "error": (str(obj.get("error"))[:160] if obj.get("error") else None),
        }
    return obj


def _iso_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        return dtparse(str(value)).date().isoformat()
    except Exception:
        return None


def _ensure_defaults(state: Dict[str, Any]) -> Dict[str, Any]:
    output = dict(state or {})
    output.setdefault("rooms", 1)
    output.setdefault("guests", 2)
    output.setdefault("required_amenities", [])
    output.setdefault("preferred_amenities", [])
    output.setdefault("sort_by", "best_value")
    output.setdefault("poi_resolved", False)
    return output


def _merge_search_args_from_state(state: Dict[str, Any]) -> Dict[str, Any]:
    current = _ensure_defaults(state)

    def canon_list(value: Any) -> List[str]:
        if not value:
            return []
        if not isinstance(value, list):
            value = [value]
        output: List[str] = []
        for item in value:
            normalized = str(item).strip().lower()
            if normalized and normalized not in output:
                output.append(normalized)
        return output

    check_in_iso = _iso_date(current.get("check_in"))
    check_out_iso = _iso_date(current.get("check_out"))
    if check_in_iso and current.get("nights"):
        try:
            check_in_date = dtparse(check_in_iso).date()
            nights = int(current["nights"])
            check_out_iso = (check_in_date + timedelta(days=nights)).isoformat()
        except Exception:
            pass

    return {
        "city": current.get("city"),
        "state": current.get("state"),
        "check_in": check_in_iso,
        "check_out": check_out_iso,
        "rooms": int(current.get("rooms") or 1),
        "guests": int(current.get("guests") or 2),
        "neighborhood": current.get("neighborhood"),
        "required_amenities": canon_list(current.get("required_amenities")),
        "preferred_amenities": canon_list(current.get("preferred_amenities")),
        "max_nightly_rate_usd": current.get("max_nightly_rate_usd"),
        "max_total_usd": current.get("max_total_usd"),
        "poi_lat": current.get("poi_lat"),
        "poi_lng": current.get("poi_lng"),
        "sort_by": current.get("sort_by") or "best_value",
    }


def _missing_required(search_args: Dict[str, Any]) -> List[str]:
    missing: List[str] = []
    if not search_args.get("city"):
        missing.append("city")
    if not search_args.get("check_in"):
        missing.append("check_in")
    if not search_args.get("check_out"):
        missing.append("check_out")
    return missing


def _question_for_missing(missing: List[str], state: Dict[str, Any]) -> str:
    missing_set = set(missing)
    if {"city", "check_in", "check_out"}.issubset(missing_set):
        if state.get("nights"):
            return (
                f"Which city are you staying in, and what check-in date should I use for "
                f"{state.get('nights')} nights?"
            )
        return "Which city are you staying in, and what are your check-in and check-out dates?"
    if "city" in missing_set and "check_in" in missing_set:
        return "Which city are you staying in, and what check-in date should I use?"
    if "city" in missing_set and "check_out" in missing_set:
        return "Which city are you staying in, and what check-out date should I use?"
    if "city" in missing_set:
        return "Which city are you staying in?"
    if "check_in" in missing_set and "check_out" in missing_set:
        if state.get("nights"):
            return f"What check-in date should I use for {state.get('nights')} nights in {state.get('city')}?"
        return f"What are your check-in and check-out dates for {state.get('city')}?"
    if "check_in" in missing_set:
        return f"What check-in date should I use for {state.get('city')}?"
    if "check_out" in missing_set:
        return f"What check-out date should I use for {state.get('city')}?"
    return "What would you like to change?"


def _tool_error_text(envelope: Dict[str, Any]) -> str:
    error = envelope.get("error")
    if error is None and envelope.get("result") is not None:
        try:
            return json.dumps(envelope.get("result"), default=str)
        except Exception:
            return str(envelope.get("result"))
    if isinstance(error, (dict, list)):
        return json.dumps(error, default=str)
    return str(error)


def _fmt_money(value: Any) -> str:
    try:
        return f"{float(value):,.2f}"
    except Exception:
        return "N/A"


def _render_hotels_from_search_response(search_response: Dict[str, Any], limit: int = 5) -> List[str]:
    if not isinstance(search_response, dict):
        return []
    matches = search_response.get("matches")
    if not isinstance(matches, list) or not matches:
        return []

    lines: List[str] = []
    for hotel in matches[:limit]:
        if not isinstance(hotel, dict):
            continue
        stars = hotel.get("stars")
        stars_text = f"{float(stars):.1f}" if isinstance(stars, (int, float)) else (str(stars) if stars is not None else "N/A")
        preferred = hotel.get("preferred_matched") or hotel.get("preferred_matched_amenities") or []
        preferred_text = f" | preferred matched: {', '.join(str(item) for item in preferred)}" if isinstance(preferred, list) and preferred else ""
        min_rooms = hotel.get("min_available_rooms_across_stay")
        min_rooms_text = f"{int(min_rooms)}" if isinstance(min_rooms, (int, float)) else "N/A"
        distance = hotel.get("distance_to_poi_miles")
        distance_text = f" | {float(distance):.2f} mi from POI" if isinstance(distance, (int, float)) else ""
        lines.append(
            f"- {hotel.get('name') or 'Unknown Hotel'} - {hotel.get('neighborhood') or 'N/A'} | "
            f"{stars_text} stars | avg ${_fmt_money(hotel.get('avg_nightly_rate_usd'))}/night | "
            f"total ${_fmt_money(hotel.get('total_usd'))} | min rooms: {min_rooms_text}{distance_text}{preferred_text}"
        )
    return lines


def _render_final_answer(explain: Dict[str, Any], search_response: Dict[str, Any]) -> str:
    narrative = (explain or {}).get("narrative") or "Here are your results."
    followup = (explain or {}).get("followup_question") or "Would you like to refine dates, neighborhood, or amenities?"
    hotel_lines = _render_hotels_from_search_response(search_response, limit=5)
    if not hotel_lines:
        refinements = (explain or {}).get("suggested_refinements") or []
        output = [narrative.strip(), ""]
        if refinements:
            output.append("Try one of these refinements:")
            for refinement in refinements[:8]:
                output.append(f"- {str(refinement).strip()}")
            output.append("")
        output.append(followup.strip())
        return "\n".join(output).strip()

    output = [narrative.strip(), "", "Top options:"]
    output.extend(hotel_lines)
    output.extend(["", followup.strip()])
    return "\n".join(output).strip()


def _build_mcp_tools() -> List[Dict[str, Any]]:
    return [
        {"type": "function", "function": {"name": "context_get", "description": "Retrieve current session state", "parameters": {"type": "object", "properties": {"session_id": {"type": "string"}}, "required": ["session_id"]}}},
        {"type": "function", "function": {"name": "context_upsert", "description": "Update session state with new values", "parameters": {"type": "object", "properties": {"session_id": {"type": "string"}, "patch": {"type": "object"}}, "required": ["session_id", "patch"]}}},
        {"type": "function", "function": {"name": "extraction_parse", "description": "Extract search parameters from user message", "parameters": {"type": "object", "properties": {"session_id": {"type": "string"}, "user_message": {"type": "string"}, "state": {"type": "object"}}, "required": ["session_id", "user_message", "state"]}}},
        {"type": "function", "function": {"name": "property_resolve", "description": "Resolve location or POI to coordinates", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "city": {"type": "string"}, "state": {"type": ["string", "null"]}, "radius_miles": {"type": "number"}}, "required": ["query", "city"]}}},
        {"type": "function", "function": {"name": "availability_search", "description": "Search for available hotels. Use this only after the user has provided a destination and dates. When the user asks for the closest or nearest matching hotel to a place, use sort_by=closest_to_poi and pass poi_lat and poi_lng after resolving the POI.", "parameters": {"type": "object", "properties": {"city": {"type": "string"}, "state": {"type": ["string", "null"]}, "check_in": {"type": "string"}, "check_out": {"type": "string"}, "rooms": {"type": "integer", "default": 1}, "guests": {"type": "integer", "default": 2}, "neighborhood": {"type": "string"}, "required_amenities": {"type": "array", "items": {"type": "string"}}, "preferred_amenities": {"type": "array", "items": {"type": "string"}}, "max_nightly_rate_usd": {"type": "number"}, "max_total_usd": {"type": "number"}, "poi_lat": {"type": "number"}, "poi_lng": {"type": "number"}, "sort_by": {"type": "string"}}, "required": ["city", "check_in", "check_out"]}}},
        {"type": "function", "function": {"name": "results_explain", "description": "Generate natural language explanation of search results", "parameters": {"type": "object", "properties": {"session_id": {"type": "string"}, "user_message": {"type": "string"}, "state": {"type": "object"}, "search_response": {"type": "object"}}, "required": ["session_id", "user_message", "state", "search_response"]}}},
    ]


def run_agentic_turn(session_id: str, user_message: str, conversation: List[dict], model: str) -> Tuple[str, List[dict], List[dict]]:
    mcp = LocalMCPClient()
    trace: List[dict] = []
    trace_id = str(uuid.uuid4())
    conversation = conversation + [{"role": "user", "content": user_message}]

    state_envelope = mcp.invoke("context.get", {"session_id": session_id}, trace_id=trace_id)
    trace.append({"step": "context_get", "result_preview": _preview(state_envelope)})
    state = state_envelope.get("result") if state_envelope.get("ok") and isinstance(state_envelope.get("result"), dict) else {}
    state = _ensure_defaults(state)

    previous_check_in = state.get("check_in")
    previous_check_out = state.get("check_out")
    previous_duration_days: Optional[int] = None
    try:
        if previous_check_in and previous_check_out:
            start = dtparse(str(previous_check_in)).date()
            end = dtparse(str(previous_check_out)).date()
            if end > start:
                previous_duration_days = (end - start).days
    except Exception:
        previous_duration_days = None

    extract_envelope = mcp.invoke("extraction.parse", {"session_id": session_id, "user_message": user_message, "state": state}, trace_id=trace_id)
    trace.append({"step": "extract", "result_preview": _preview(extract_envelope)})
    if not extract_envelope.get("ok"):
        trace.append({"step": "extract_failed", "error": _tool_error_text(extract_envelope)})

    patch: Dict[str, Any] = {}
    if extract_envelope.get("ok") and isinstance(extract_envelope.get("result"), dict):
        maybe_patch = extract_envelope["result"].get("patch")
        if isinstance(maybe_patch, dict):
            patch = maybe_patch

    if patch:
        upsert_envelope = mcp.invoke("context.upsert", {"session_id": session_id, "patch": patch}, trace_id=trace_id)
        trace.append({"step": "context_upsert", "result_preview": _preview(upsert_envelope)})
        if not upsert_envelope.get("ok"):
            assistant_text = "I couldn't update session context. Tool error:\n" + _tool_error_text(upsert_envelope)
            conversation = conversation + [{"role": "assistant", "content": assistant_text}]
            trace.append({"step": "assistant_response", "result_preview": assistant_text[:200]})
            return assistant_text, conversation, trace

    refreshed_state_envelope = mcp.invoke("context.get", {"session_id": session_id}, trace_id=trace_id)
    trace.append({"step": "context_get_after_upsert", "result_preview": _preview(refreshed_state_envelope)})
    if refreshed_state_envelope.get("ok") and isinstance(refreshed_state_envelope.get("result"), dict):
        state = refreshed_state_envelope["result"]
    state = _ensure_defaults(state)

    try:
        check_in = state.get("check_in")
        check_out = state.get("check_out")
        patch_set_check_out = "check_out" in patch
        check_in_date = dtparse(str(check_in)).date() if check_in else None
        check_out_date = dtparse(str(check_out)).date() if check_out else None
        reducer_patch: Dict[str, Any] = {}
        if check_in_date and check_out_date and check_out_date > check_in_date and not state.get("nights"):
            reducer_patch["nights"] = (check_out_date - check_in_date).days
        check_in_changed = bool(previous_check_in) and bool(check_in) and str(previous_check_in) != str(check_in)
        if check_in_changed and not patch_set_check_out and check_in_date and (check_out_date is None or check_out_date <= check_in_date):
            nights = state.get("nights") or previous_duration_days
            if nights:
                reducer_patch["check_out"] = (check_in_date + timedelta(days=int(nights))).isoformat()
                reducer_patch["nights"] = int(nights)
        if reducer_patch:
            reducer_envelope = mcp.invoke("context.upsert", {"session_id": session_id, "patch": reducer_patch}, trace_id=trace_id)
            trace.append({"step": "date_reducer_upsert", "result_preview": _preview(reducer_envelope)})
            refreshed = mcp.invoke("context.get", {"session_id": session_id}, trace_id=trace_id)
            trace.append({"step": "context_get_after_date_reducer", "result_preview": _preview(refreshed)})
            if refreshed.get("ok") and isinstance(refreshed.get("result"), dict):
                state = refreshed["result"]
            state = _ensure_defaults(state)
    except Exception as exc:
        trace.append({"step": "date_reducer_failed", "error": str(exc)})

    poi_query = state.get("poi_query")
    poi_resolved = bool(state.get("poi_resolved"))
    last_resolved = state.get("poi_last_resolved_query")
    should_resolve = bool(poi_query) and bool(state.get("city")) and (not poi_resolved or last_resolved != poi_query)
    if should_resolve:
        trace.append({"step": "decision", "reason": "poi detected in user intent, resolving location before hotel search", "poi_query": poi_query})
        property_envelope = mcp.invoke(
            "property.resolve",
            {"query": poi_query, "city": state.get("city"), "state": state.get("state"), "radius_miles": state.get("poi_radius_miles")},
            trace_id=trace_id,
        )
        trace.append({"step": "property_resolve", "result_preview": _preview(property_envelope)})
        if property_envelope.get("ok") and isinstance(property_envelope.get("result"), dict):
            result = property_envelope["result"]
            secondary_patch: Dict[str, Any] = {"poi_lat": result.get("lat"), "poi_lng": result.get("lng"), "poi_resolved": True, "poi_last_resolved_query": poi_query}
            if not state.get("neighborhood") and result.get("recommended_neighborhood"):
                secondary_patch["neighborhood"] = result.get("recommended_neighborhood")
            update_envelope = mcp.invoke("context.upsert", {"session_id": session_id, "patch": secondary_patch}, trace_id=trace_id)
            trace.append({"step": "context_upsert_after_property_resolve", "result_preview": _preview(update_envelope)})
            refreshed = mcp.invoke("context.get", {"session_id": session_id}, trace_id=trace_id)
            trace.append({"step": "context_get_after_property_resolve", "result_preview": _preview(refreshed)})
            if refreshed.get("ok") and isinstance(refreshed.get("result"), dict):
                state = refreshed["result"]
            state = _ensure_defaults(state)
        else:
            trace.append({"step": "property_resolve_failed", "error": _tool_error_text(property_envelope)})

    search_args = _merge_search_args_from_state(state)
    if search_args.get("sort_by") == "closest_to_poi" and search_args.get("poi_lat") is not None and search_args.get("poi_lng") is not None:
        trace.append(
            {
                "step": "decision",
                "reason": "ranking matching hotels by distance because user asked for the closest hotel to a POI",
                "poi_query": state.get("poi_query"),
            }
        )
    missing = _missing_required(search_args)
    if missing:
        assistant_text = _question_for_missing(missing, state)
        conversation = conversation + [{"role": "assistant", "content": assistant_text}]
        trace.append({"step": "assistant_response", "result_preview": assistant_text[:200]})
        return assistant_text, conversation, trace

    availability_envelope = mcp.invoke("availability.search", search_args, trace_id=trace_id)
    trace.append({"step": "availability_search", "result_preview": _preview(availability_envelope)})
    if not availability_envelope.get("ok"):
        assistant_text = "I couldn't run availability.search. Tool error:\n" + _tool_error_text(availability_envelope)
        conversation = conversation + [{"role": "assistant", "content": assistant_text}]
        trace.append({"step": "assistant_response", "result_preview": assistant_text[:200]})
        return assistant_text, conversation, trace

    search_response = availability_envelope.get("result") if isinstance(availability_envelope.get("result"), dict) else {}
    explain_envelope = mcp.invoke(
        "results.explain",
        {"session_id": session_id, "user_message": user_message, "state": state, "search_response": search_response},
        trace_id=trace_id,
    )
    trace.append({"step": "results_explain", "result_preview": _preview(explain_envelope)})
    if not explain_envelope.get("ok"):
        assistant_text = "I ran availability.search, but results.explain failed. Tool error:\n" + _tool_error_text(explain_envelope)
        conversation = conversation + [{"role": "assistant", "content": assistant_text}]
        trace.append({"step": "assistant_response", "result_preview": assistant_text[:200]})
        return assistant_text, conversation, trace

    explain = explain_envelope.get("result") if isinstance(explain_envelope.get("result"), dict) else {}
    assistant_text = _render_final_answer(explain, search_response)
    conversation = conversation + [{"role": "assistant", "content": assistant_text}]
    trace.append({"step": "assistant_response", "result_preview": assistant_text[:200]})
    return assistant_text, conversation, trace


def run_react_turn(session_id: str, user_message: str, conversation: List[dict], model: str, max_iterations: int = 10) -> Tuple[str, List[dict], List[dict]]:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    mcp = LocalMCPClient()
    trace: List[dict] = []
    trace_id = str(uuid.uuid4())
    current_state: Dict[str, Any] = {}
    last_search_response: Dict[str, Any] = {}
    messages = [{"role": "system", "content": REACT_SYSTEM_PROMPT}]
    messages.extend(conversation)
    messages.append({"role": "user", "content": user_message})
    tools = _build_mcp_tools()

    for iteration in range(max_iterations):
        trace.append({"step": f"iteration_{iteration}", "action": "llm_call"})
        try:
            response = client.chat.completions.create(model=model, messages=messages, tools=tools, tool_choice="auto", temperature=0.1)
        except Exception as exc:
            error_message = f"LLM call failed: {exc}"
            trace.append({"step": "llm_error", "error": error_message})
            return error_message, conversation + [{"role": "user", "content": user_message}], trace

        assistant_message = response.choices[0].message
        if not assistant_message.tool_calls:
            final_answer = assistant_message.content or "I couldn't complete your request."
            conversation.append({"role": "user", "content": user_message})
            conversation.append({"role": "assistant", "content": final_answer})
            trace.append({"step": "final_answer", "content": final_answer[:200]})
            return final_answer, conversation, trace

        messages.append({"role": "assistant", "content": assistant_message.content, "tool_calls": [{"id": call.id, "type": "function", "function": {"name": call.function.name, "arguments": call.function.arguments}} for call in assistant_message.tool_calls]})
        for tool_call in assistant_message.tool_calls:
            function_name = tool_call.function.name
            if function_name.startswith("functions."):
                function_name = function_name.replace("functions.", "")
            capability = function_name.replace("_", ".", 1)
            try:
                arguments = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                arguments = {}

            if capability in {"context.get", "context.upsert"} and not arguments.get("session_id"):
                arguments["session_id"] = session_id
            elif capability == "extraction.parse":
                arguments.setdefault("session_id", session_id)
                arguments.setdefault("user_message", user_message)
                arguments.setdefault("state", current_state)
            elif capability == "availability.search":
                defaults = _merge_search_args_from_state(current_state)
                for key, value in defaults.items():
                    if arguments.get(key) is None and value is not None:
                        arguments[key] = value
                if arguments.get("sort_by") == "closest_to_poi" and current_state.get("poi_query"):
                    trace.append(
                        {
                            "step": f"decision_{iteration}",
                            "reason": "ranking matching hotels by distance because user asked for the closest hotel to a POI",
                            "poi_query": current_state.get("poi_query"),
                        }
                    )
            elif capability == "results.explain":
                arguments.setdefault("session_id", session_id)
                arguments.setdefault("user_message", user_message)
                arguments.setdefault("state", current_state)
                arguments.setdefault("search_response", last_search_response)

            trace.append({"step": f"tool_call_{iteration}", "capability": capability, "arguments": arguments})
            result_envelope = mcp.invoke(capability, arguments, trace_id=trace_id)
            if capability == "context.get":
                if result_envelope.get("ok") and isinstance(result_envelope.get("result"), dict):
                    current_state = result_envelope["result"]
                else:
                    current_state = {"rooms": 1, "guests": 2, "sort_by": "best_value"}
                    result_envelope["ok"] = True
                    result_envelope["result"] = current_state
            elif capability == "context.upsert" and result_envelope.get("ok") and isinstance(result_envelope.get("result"), dict):
                state_payload = result_envelope["result"].get("state")
                if isinstance(state_payload, dict):
                    current_state = state_payload
            elif capability == "property.resolve" and result_envelope.get("ok") and isinstance(result_envelope.get("result"), dict):
                resolved = result_envelope["result"]
                current_state = {
                    **current_state,
                    "poi_lat": resolved.get("lat"),
                    "poi_lng": resolved.get("lng"),
                    "poi_resolved": True,
                    "poi_last_resolved_query": current_state.get("poi_query"),
                    "neighborhood": current_state.get("neighborhood") or resolved.get("recommended_neighborhood"),
                }
            elif capability == "availability.search" and result_envelope.get("ok") and isinstance(result_envelope.get("result"), dict):
                last_search_response = result_envelope["result"]

            tool_result = json.dumps(result_envelope.get("result"), default=str) if result_envelope.get("ok") else f"Error: {result_envelope.get('error', 'Unknown error')}"
            trace.append({"step": f"tool_result_{iteration}", "capability": capability, "ok": result_envelope.get("ok"), "result_preview": tool_result[:200]})
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": tool_result})

    fallback = "I've tried multiple steps but couldn't complete your request. Please try rephrasing."
    conversation.append({"role": "user", "content": user_message})
    conversation.append({"role": "assistant", "content": fallback})
    trace.append({"step": "max_iterations_reached", "iterations": max_iterations})
    return fallback, conversation, trace


def chat(request: ChatRequest) -> ChatResponse:
    conversation = CONVERSATIONS.get(request.session_id, [])
    assistant_text, updated_conversation, trace = run_agentic_turn(request.session_id, request.message, conversation, MODEL)
    CONVERSATIONS[request.session_id] = updated_conversation
    return ChatResponse(session_id=request.session_id, assistant_message=assistant_text, trace=trace)


def chat_react(request: ChatRequest) -> ChatResponse:
    key = request.session_id + "_react"
    conversation = CONVERSATIONS.get(key, [])
    assistant_text, updated_conversation, trace = run_react_turn(request.session_id, request.message, conversation, MODEL)
    CONVERSATIONS[key] = updated_conversation
    return ChatResponse(session_id=request.session_id, assistant_message=assistant_text, trace=trace)

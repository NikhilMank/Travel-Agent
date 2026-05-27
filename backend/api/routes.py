from fastapi import APIRouter, HTTPException

from ..models.schemas import ChatRequest, ChatResponse
from ..agent.graph import compile_agent, run_agent
from ..agent.nodes import extract_text_from_response

router = APIRouter()

_agent = None


def get_agent():
    global _agent
    if _agent is None:
        _agent = compile_agent()
    return _agent


@router.post("/chat/welcome")
async def welcome():
    return ChatResponse(
        response="Hi! I'm your travel agent assistant. I'll help you plan your perfect trip. Where would you like to go?",
        is_complete=False,
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        agent = get_agent()

        result = run_agent(agent, request.message, request.session_id)

        messages = result.get("messages", [])
        response_text = ""
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type == "ai":
                response_text = extract_text_from_response(msg)
                break

        if not response_text:
            for msg in reversed(messages):
                response_text = extract_text_from_response(msg)
                if response_text:
                    break

        is_planning = result.get("is_ready_for_planning", False)

        tool_calls = []
        for msg in messages:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls.append(tc.get("name", "unknown"))

        worker_calls = []
        worker_sources = []
        for wr in result.get("worker_results", []):
            w = wr.get("worker", "")
            if w:
                worker_calls.append(w)
                source = wr.get("source", "training_data")
                worker_sources.append(f"{w.replace('_worker', '').replace('_', ' ').title()}: {source}")

        print(f"Response: {response_text[:100]}...")
        print(f"Tool calls: {tool_calls}")
        print(f"Worker sources: {worker_sources}")

        return ChatResponse(
            response=response_text,
            is_complete=is_planning,
            tool_calls=tool_calls,
            worker_calls=worker_calls,
            worker_sources=worker_sources,
        )

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error in chat endpoint: {error_details}")
        raise HTTPException(status_code=500, detail=str(e))

import json
from typing import List, Dict, Any

from langchain_core.messages import SystemMessage, ToolMessage, RemoveMessage
from langchain_core.tools import tool
from langchain.agents import create_agent
from langchain.agents.factory import AgentMiddleware

from .nodes import create_llm, extract_text_from_response
from .state import AgentState, REQUIRED_FIELDS


DYNAMIC_SYSTEM_ID = "dynamic_state_info"


@tool
def mark_ready_for_planning(required_info: Dict[str, Any], additional_info: Dict[str, Any]) -> str:
    """TRIGGER the trip planning engine to generate the complete plan.

    CALL THIS TOOL when ALL required info is gathered AND the user has confirmed they're ready.
    Do NOT generate a trip plan yourself — calling this tool will trigger the planning system
    which creates the full itinerary with real-time data.

    Args:
        required_info: Must include start_location, destination, start_date, end_date, travelers, budget_range
        additional_info: Any extra preferences (preferences, accommodation details, etc.)
    """
    missing = [f for f in REQUIRED_FIELDS if not required_info.get(f)]
    if missing:
        return f"Cannot mark ready -- missing required fields: {', '.join(missing)}"
    return "READY"


class DynamicPromptMiddleware(AgentMiddleware):
    state_schema = AgentState

    def before_agent(self, state: AgentState, runtime) -> Dict[str, Any]:
        required = state.get("required_info", {})
        additional = state.get("additional_info", {})

        known = {k: v for k, v in required.items() if v is not None}
        known["preferences"] = additional.get("preferences", [])
        filled = [f for f in REQUIRED_FIELDS if required.get(f)]
        missing = [f for f in REQUIRED_FIELDS if not required.get(f)]

        system_content = (
            f"You are a friendly travel agent helping a user plan their trip.\n\n"
            f"Currently known: {json.dumps(known, indent=2)}\n"
            f"Fields filled: {filled}\n"
            f"Fields still needed: {missing}\n\n"
            f"Your job is to have a natural conversation to gather the missing info.\n"
            f"- Ask ONE question at a time. Never list multiple questions.\n"
            f'- When the user provides dates like "05.06.2026", note that 05 could be day or month (both <= 12) -- ask for clarification before proceeding.\n'
            f'- When the user mentions vague terms like "budget" or "moderate" for budget, ask for a specific number.\n'
            f'- For travelers: if the user says "I" or "me", ask if they\'re traveling alone or with others. Do NOT assume they\'re solo.\n'
            f'- For start_location: if the user doesn\'t mention where they\'re traveling FROM, ask "Where are you departing from?"\n'
                f"- Once all required fields are filled, ask about preferences: 'Any preferences on activities, cities to visit, or accommodation style?'\n"
            f"- After the user answers preferences (or says none), recap everything and ask: 'Shall I proceed with planning?'\n"
            f"- Wait for an explicit YES (e.g., 'yes', 'go ahead', 'sure'). If the user gives more details instead of confirming, ask again.\n\n"
            f"Required fields: start_location, destination, start_date, end_date, travelers, budget_range\n"
            f"Be conversational. Keep questions short and friendly.\n\n"
            f"--- HOW TO FINISH ---\n"
            f"When the user explicitly says YES to proceeding, call `mark_ready_for_planning` with the complete `required_info` and `additional_info`.\n"
            f"Do NOT write any trip plan yourself — this tool triggers the planning engine.\n"
            f"After calling it, reply: \"Planning your trip now...\""
        )

        updates: List = [SystemMessage(content=system_content, id=DYNAMIC_SYSTEM_ID)]

        messages = state.get("messages", [])
        for m in messages:
            if getattr(m, "id", None) == DYNAMIC_SYSTEM_ID:
                updates.insert(0, RemoveMessage(id=DYNAMIC_SYSTEM_ID))
                break

        return {"messages": updates}


def create_react_agent_node():
    llm = create_llm(temperature=0.7)
    tools = [mark_ready_for_planning]

    agent = create_agent(
        model=llm,
        tools=tools,
        state_schema=AgentState,
        middleware=[DynamicPromptMiddleware()],
    )

    return agent


def extract_info_from_conversation(messages: List) -> Dict[str, Any]:
    """Extract structured info from conversation messages using an LLM."""
    llm = create_llm(temperature=0.1)

    history_lines = []
    for m in messages:
        if hasattr(m, 'type') and hasattr(m, 'content'):
            history_lines.append(f"{m.type}: {m.content}")
        elif isinstance(m, dict):
            history_lines.append(f"{m.get('role', 'unknown')}: {m.get('content', '')}")
    history_str = "\n".join(history_lines)

    prompt = f"""Extract trip planning information from this conversation.

Conversation:
{history_str}

Return a JSON object with exactly these fields (use null if not mentioned):
- "start_location": The city/country they're departing from. null if not mentioned.
- "destination": The country or city they want to travel to (extract literally, no extra text)
- "start_date": The start date of the trip (exact text from user)
- "end_date": The end/return date of the trip (exact text from user)
- "travelers": null or a JSON object with key "num_people" (integer). ONLY set if there is explicit evidence of other people (e.g. "we", "girlfriend", "family", "friends", "us", "our"). Set to null if the user only says "I", "me", or "my".
- "budget_range": Exact budget string as mentioned e.g. "600 euros". null if not mentioned.
- "preferences": A list of interests explicitly mentioned. null if none.

Return ONLY valid JSON with no explanation, no markdown formatting, no extra text."""

    response = llm.invoke(prompt)
    text = extract_text_from_response(response)

    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return {}


def post_process_extraction(state: AgentState) -> Dict[str, Any]:
    messages = state.get("messages", [])
    required_info = dict(state.get("required_info", {}))
    additional_info = dict(state.get("additional_info", {}))

    is_ready = False

    for msg in reversed(messages):
        if isinstance(msg, ToolMessage) and msg.name == "mark_ready_for_planning":
            if msg.content == "READY":
                is_ready = True
                break

    if not is_ready:
        extracted = extract_info_from_conversation(messages)

        for key in REQUIRED_FIELDS:
            val = extracted.get(key)
            if val is None or val == "null":
                continue
            if key == "destination" and required_info.get(key) is not None:
                continue
            required_info[key] = val

        prefs = extracted.get("preferences")
        if prefs:
            existing = set(str(p).lower() for p in additional_info.get("preferences", []))
            new = [p for p in prefs if str(p).lower() not in existing]
            if new:
                additional_info.setdefault("preferences", [])
                additional_info["preferences"] += new

        travelers = extracted.get("travelers")
        if required_info.get("travelers"):
            pass
        elif isinstance(travelers, dict) and travelers.get("num_people"):
            required_info["travelers"] = travelers
        elif isinstance(travelers, int):
            required_info["travelers"] = {"num_people": travelers}

        if not is_ready and all(required_info.get(f) for f in REQUIRED_FIELDS):
            is_ready = True
            last_ai = next((m for m in reversed(messages) if m.type == "ai" and m.content), None)
            if last_ai and last_ai.content.strip().endswith("?"):
                is_ready = False
            if is_ready:
                last_human = next((m for m in reversed(messages) if m.type == "human" and m.content), None)
                if last_human:
                    text = last_human.content.strip().lower()
                    confirmations = {"yes", "yeah", "yep", "sure", "ok", "okay", "go ahead", "proceed", "correct", "that's all", "that is all", "done", "confirmed", "looks good"}
                    is_confirm = any(
                        text == w or text.startswith(w + " ") or text.startswith(w + ",")
                        for w in confirmations
                    )
                    if not is_confirm:
                        is_ready = False

    return {
        "required_info": required_info,
        "additional_info": additional_info,
        "is_ready_for_planning": is_ready,
    }

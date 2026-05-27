from typing import TypedDict, Annotated, Optional
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list[HumanMessage | AIMessage], add_messages]
    required_info: dict
    additional_info: dict
    missing_required_fields: list[str]
    is_ready_for_planning: bool
    worker_results: list[dict]
    workers: list[dict]


REQUIRED_FIELDS = [
    "start_location",
    "destination",
    "start_date",
    "end_date",
    "travelers",
    "budget_range",
]

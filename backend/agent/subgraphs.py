import json
from typing import Dict, Any
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import HumanMessage, AIMessage

from .state import AgentState
from .react_agent import create_react_agent_node, post_process_extraction


def generate_welcome(state: AgentState) -> Dict[str, Any]:
    return {
        "messages": [AIMessage(content="Hi! I'm your travel agent assistant. I'll help you plan your perfect trip. Where would you like to go?")],
    }


def route_from_start(state: AgentState) -> str:
    messages = state.get("messages", [])
    if len(messages) == 1 and isinstance(messages[0], HumanMessage) and not messages[0].content.strip():
        return "welcome"
    return "react_agent"


def should_continue(state: AgentState) -> str:
    """After post_process, route to END or orchestrator."""
    if state.get("is_ready_for_planning"):
        return "end"
    return "end"


def create_detail_gathering_subgraph() -> StateGraph:
    subgraph = StateGraph(AgentState)

    react_agent = create_react_agent_node()

    subgraph.add_node("welcome", generate_welcome)
    subgraph.add_node("react_agent", react_agent)
    subgraph.add_node("post_process", post_process_extraction)

    subgraph.add_conditional_edges(
        START,
        route_from_start,
        {
            "welcome": "welcome",
            "react_agent": "react_agent",
        }
    )

    subgraph.add_edge("react_agent", "post_process")

    subgraph.add_conditional_edges(
        "post_process",
        should_continue,
        {
            "end": END,
        }
    )

    subgraph.add_edge("welcome", END)

    return subgraph.compile()

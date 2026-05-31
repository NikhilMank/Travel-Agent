import json
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage

from .dynamodb_checkpoint import DynamoDBSaver

from .state import AgentState
from .nodes import orchestrator_node, worker_node, reducer_node
from .subgraphs import create_detail_gathering_subgraph


def create_agent() -> StateGraph:
    graph = StateGraph(AgentState)

    detail_gathering_subgraph = create_detail_gathering_subgraph()
    graph.add_node("detail_gathering", detail_gathering_subgraph)
    graph.add_node("orchestrator", orchestrator_wrapper)
    graph.add_node("reducer", reducer_wrapper)

    graph.set_entry_point("detail_gathering")

    graph.add_conditional_edges(
        "detail_gathering",
        lambda state: "orchestrator" if state.get("is_ready_for_planning") else END,
        {
            "orchestrator": "orchestrator",
            END: END,
        }
    )

    graph.add_edge("orchestrator", "reducer")
    graph.add_edge("reducer", END)

    checkpointer = DynamoDBSaver()
    return graph.compile(checkpointer=checkpointer)


def compile_agent():
    """Create and compile the full agent graph once."""
    return create_agent()


def run_agent(agent, user_message: str, session_id: str) -> AgentState:
    config = {"configurable": {"thread_id": session_id}}

    messages = [HumanMessage(content=user_message)]
    if not user_message.strip():
        messages = [HumanMessage(content="")]

    result = agent.invoke(
        {"messages": messages},
        config,
    )

    return result


def orchestrator_wrapper(state: AgentState) -> Dict[str, Any]:
    worker_config = orchestrator_node(state)
    workers_list = worker_config.get("workers", [])

    results = [None] * len(workers_list)
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(worker_node, w.get("worker_name", "unknown"), w.get("task", "")): i
            for i, w in enumerate(workers_list)
        }
        for future in as_completed(futures):
            idx = futures[future]
            results[idx] = future.result()

    return {"worker_results": results}


def reducer_wrapper(state: AgentState) -> AgentState:
    worker_results = state.get("worker_results", [])
    return reducer_node(state, worker_results)
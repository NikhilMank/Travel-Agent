import os
import json
import time
from typing import List, Dict, Any

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from langchain_core.messages import AIMessage
from langchain_core.prompts import PromptTemplate

from ..models.schemas import ExtractedTripInfo
from .state import AgentState


def create_llm(temperature: float = 0.7, max_tokens: int = 4096):
    from langchain_aws import ChatBedrock

    return ChatBedrock(
        model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        temperature=temperature,
        max_tokens=max_tokens,
        region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
    )


def extract_text_from_response(response) -> str:
    content = getattr(response, 'content', str(response))
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                if block.get('type') == 'text':
                    return block.get('text', '')
                if 'text' in block:
                    return block['text']
    return str(response)


def web_search(query: str, max_results: int = 5) -> tuple:
    """Search the web via Tavily, falling back to DuckDuckGo on failure.
    Returns (results_text, engine_name) where engine_name is 'tavily', 'duckduckgo', or ''."""
    results = _tavily_search(query, max_results)
    if results:
        return results, "tavily"
    results = _duckduckgo_search(query, max_results)
    if results:
        return results, "duckduckgo"
    return "", ""


def _tavily_search(query: str, max_results: int = 5) -> str:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key or api_key == "your_tavily_api_key_here":
        return ""
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
        response = client.search(query=query, max_results=max_results)
        snippets = []
        for result in response.get("results", []):
            title = result.get("title", "")
            content = result.get("content", "")
            url = result.get("url", "")
            snippets.append(f"**{title}**\n{content}\nSource: {url}")
        return "\n\n".join(snippets)
    except Exception as e:
        print(f"Tavily search failed: {e}")
        return ""


def _duckduckgo_search(query: str, max_results: int = 5) -> str:
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        snippets = []
        for r in results:
            title = r.get("title", "")
            body = r.get("body", "")
            href = r.get("href", "")
            snippets.append(f"**{title}**\n{body}\nSource: {href}")
        return "\n\n".join(snippets)
    except Exception as e:
        print(f"DuckDuckGo search failed: {e}")
        return ""


def orchestrator_node(state: AgentState) -> Dict[str, Any]:
    llm = create_llm()
    required_info = state.get("required_info", {})
    additional_info = state.get("additional_info", {})

    orchestrator_template = PromptTemplate.from_template("""You are the orchestrator for a travel planning agent.

Analyze the trip details and decide what workers/tasks are needed:

Required Info:
{required_info_json}

Additional Info:
{additional_info_json}

Return a JSON list of workers. Example:
[
  {{"worker_name": "attractions_worker", "task": "Find top attractions", "priority": "high"}},
  {{"worker_name": "food_worker", "task": "Find restaurants", "priority": "medium"}}
]

Return ONLY valid JSON.""")

    system_prompt = orchestrator_template.format(
        required_info_json=json.dumps(required_info, indent=2),
        additional_info_json=json.dumps(additional_info, indent=2),
    )

    try:
        response = llm.invoke(system_prompt)
        content = extract_text_from_response(response).strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        workers = json.loads(content)
        return {"workers": workers}
    except Exception as e:
        if "ThrottlingException" in str(e):
            time.sleep(2)
            try:
                response = llm.invoke(system_prompt)
                content = extract_text_from_response(response).strip()
                if content.startswith("```json"):
                    content = content[7:]
                if content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                workers = json.loads(content)
                return {"workers": workers}
            except:
                pass
        print(f"Error in orchestrator: {e}")
        return {"workers": []}


def worker_node(worker_name: str, task: str) -> Dict[str, Any]:
    llm = create_llm()
    search_results, search_engine = web_search(task)

    if search_results:
        worker_template = PromptTemplate.from_template("""You are a {worker_name}.

Your task is: {task}

REAL-TIME WEB SEARCH RESULTS:
{search_results}

Use the search results above as your primary source. Include specific names, prices, URLs, and details found in the results.
If the search results don't have enough detail, supplement with your general knowledge.
Provide a thorough, specific response.""")
    else:
        worker_template = PromptTemplate.from_template("""You are a {worker_name}.

Your task is: {task}

Provide detailed information based on your knowledge. Be specific and helpful.""")

    system_prompt = worker_template.format(
        worker_name=worker_name,
        task=task,
        search_results=search_results,
    )

    for attempt in range(3):
        try:
            response = llm.invoke(system_prompt)
            source = search_engine if search_results else "training_data"
            return {
                "worker": worker_name,
                "task": task,
                "result": extract_text_from_response(response),
                "status": "completed",
                "source": source,
            }
        except Exception as e:
            if "ThrottlingException" in str(e) and attempt < 2:
                wait = 2 ** attempt
                print(f"Throttled: {worker_name}, retrying in {wait}s")
                time.sleep(wait)
                continue
            return {
                "worker": worker_name,
                "task": task,
                "result": f"Error: {str(e)}",
                "status": "failed",
                "source": "error",
            }


def reducer_node(state: AgentState, worker_results: List[Dict[str, Any]]) -> AgentState:
    llm = create_llm(max_tokens=8192)
    required_info = state.get("required_info", {})
    additional_info = state.get("additional_info", {})

    combined_results = "\n\n".join([
        f"=== {r['worker']} ===\n{r['result']}"
        for r in worker_results
    ])

    reducer_template = PromptTemplate.from_template("""You are a travel planning expert. Create a comprehensive trip plan.

REQUIRED INFORMATION:
{required_info_json}

ADDITIONAL INFORMATION:
{additional_info_json}

WORKER RESULTS:
{combined_results}

Create a detailed trip plan with:
1. Friendly greeting
2. Day-by-day itinerary
3. Accommodation options
4. Budget breakdown
5. Tips

Make it comprehensive. Use **bold** for important info.""")

    system_prompt = reducer_template.format(
        required_info_json=json.dumps(required_info, indent=2),
        additional_info_json=json.dumps(additional_info, indent=2),
        combined_results=combined_results,
    )

    for attempt in range(2):
        try:
            response = llm.invoke(system_prompt)
            response_text = extract_text_from_response(response)

            return {
                "messages": state["messages"] + [AIMessage(content=response_text)],
                "required_info": required_info,
                "additional_info": additional_info,
                "missing_required_fields": [],
                "is_ready_for_planning": False,
            }
        except Exception as e:
            if "ThrottlingException" in str(e) and attempt == 0:
                time.sleep(2)
                continue
            print(f"Error in reducer: {e}")
            return {
                "messages": state["messages"] + [AIMessage(content="Sorry, I couldn't generate the trip plan.")],
                "required_info": required_info,
                "additional_info": additional_info,
                "missing_required_fields": [],
                "is_ready_for_planning": False,
            }

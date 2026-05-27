# Travel Agent — AI Trip Planner

An AI-powered travel agent that plans complete trips through natural conversation. Built with **LangGraph**, **LangChain**, and **Claude Haiku 4.5** on Amazon Bedrock. The agent gathers trip details conversationally, then orchestrates parallel web-search workers to produce a comprehensive, real-time itinerary.

---

## Architecture

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         FastAPI (backend/main.py)                       │
│  POST /api/chat { message, session_id } → run_agent() → ChatResponse   │
└───────────────────────────┬─────────────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────────────┐
│                     LangGraph Parent Graph (graph.py)                   │
│                                                                         │
│  START → detail_gathering (subgraph) ──is_ready?──→ orchestrator →     │
│                                          │                             │
│                                          ▼                             │
│                                         END (back to user)             │
│                                                       │                │
│                                                       ▼                │
│                                           reducer → END (return plan)  │
└─────────────────────────────────────────────────────────────────────────┘
```

Each user message triggers a full graph invocation. The checkpointer (`InMemorySaver`) persists state between turns via `thread_id`, so the conversation accumulates naturally.

---

### Component Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                    backend/agent/                                │
│  ┌─────────────┐   ┌─────────────────┐   ┌───────────────────┐  │
│  │  state.py    │   │  react_agent.py  │   │    nodes.py       │  │
│  │  AgentState  │◄──│  Agent + Extract │   │  Orchestrator     │  │
│  │  TypedDict   │   │  + PostProcess  │──►│  Workers (LLM)    │  │
│  │              │   │                  │   │  Reducer (LLM)    │  │
│  └─────────────┘   └─────────────────┘   │  Web Search       │  │
│                                           │  (Tavily → DDG)   │  │
│                                           └───────────────────┘  │
│  ┌─────────────────┐   ┌─────────────────┐                       │
│  │  subgraphs.py   │   │    graph.py      │                      │
│  │  DetailGathering│──►│  Parent Graph    │                      │
│  │  subgraph       │   │  + Checkpointer  │                      │
│  └─────────────────┘   └─────────────────┘                       │
└──────────────────────────────────────────────────────────────────┘
         │                          │
         ▼                          ▼
┌─────────────────┐   ┌──────────────────────────┐
│  backend/api/    │   │     frontend/             │
│  routes.py       │   │     app.py (Streamlit)   │
│  FastAPI router  │◄──│──────────────────────────│
└─────────────────┘   └──────────────────────────┘
```

---

### Graph Structure in Detail

#### 1. Detail-Gathering Subgraph (`subgraphs.py`)

```
START → route_from_start ─── "welcome" ──→ welcome ──→ END
                           │
                           └── "react_agent" ──→ react_agent ──→ post_process ──→ END
```

| Node | File:Line | What it does |
|------|-----------|-------------|
| `welcome` | `subgraphs.py:10` | Returns a hardcoded greeting `AIMessage` on first load |
| `react_agent` | `react_agent.py:77` | The conversational LLM agent (see below) |
| `post_process` | `react_agent.py:132` | Runs extraction LLM, merges info into state, detects readiness |

The subgraph always returns to `END`. The parent graph handles the orchestrator routing based on `is_ready_for_planning`.

#### 2. Parent Graph (`graph.py`)

```
START → detail_gathering ──is_ready_for_planning?──→ orchestrator ──→ reducer ──→ END
                          │
                          └── False ──→ END (return to user)
```

The conditional edge checks `state.is_ready_for_planning` after each detail-gathering pass. When `True`, the planner pipeline runs.

#### 3. Planner Pipeline (`nodes.py`)

```
orchestrator_node ──→ worker_node × N (parallel) ──→ reducer_node
```

| Node | What it does |
|------|-------------|
| `orchestrator_node` | LLM analyzes trip details and generates a list of worker tasks (JSON) |
| `worker_node` | For each worker: web search → LLM prompt with results → structured output |
| `reducer_node` | LLM synthesizes all worker outputs into a formatted trip plan |

Workers run in parallel via `ThreadPoolExecutor(max_workers=8)` in `orchestrator_wrapper`.

---

### Data Flow End-to-End

```
User: "I want to go to Italy from Germany"
  │
  ▼
POST /api/chat { message, session_id }
  │
  ▼
run_agent() → graph.invoke({messages: [HumanMessage]}, {thread_id: session_id})
  │
  ▼
START → detail_gathering subgraph
  │
  ▼
route_from_start → "react_agent"
  │
  ▼
DynamicPromptMiddleware fires (react_agent.py:37):
  - Reads current required_info, additional_info from state
  - Builds SystemMessage:
      "Currently known: {destination: Italy, start_location: Germany}
       Fields filled: [destination, start_location]
       Fields still needed: [start_date, end_date, travelers, budget_range]
       Ask ONE question at a time..."
  - Removes previous SystemMessage via RemoveMessage(id=DYNAMIC_SYSTEM_ID)
  - Injects new SystemMessage into message list
  │
  ▼
Agent (Claude Haiku) responds:
  "Great! When are you planning to start your trip?"
  │
  ▼
post_process_extraction (react_agent.py:132):
  1. Check for mark_ready_for_planning tool call in messages
  2. Call extract_info_from_conversation() — separate LLM call, temperature 0.1
     Returns: {destination: "Italy", start_location: "Germany", ...}
  3. Merge extracted values into state.required_info (keeps existing, adds new)
  4. Merge preferences (deduplicated)
  5. Detect readiness:
     - All REQUIRED_FIELDS filled?
     - Last AI message not ending with "?"?
     - Last human message is a confirmation (yes/go ahead)?
     → Sets is_ready_for_planning = True/False
  │
  ▼
Subgraph returns → Parent graph checks is_ready_for_planning
  │
  ├── False → END → return to user (API picks last AI message)
  │
  └── True → orchestrator_node:
      LLM generates worker list:
      [
        {"worker_name": "flights_worker", "task": "Find flights from Berlin to Italy..."},
        {"worker_name": "accommodation_worker", "task": "Find budget hotels..."},
        ...
      ]
      │
      ▼
      ThreadPoolExecutor(max_workers=8):
        worker_node("flights_worker", task):
          1. web_search(task) → Tavily → DuckDuckGo → ""
          2. LLM prompt = task + search_results
          3. Returns {worker, task, result, status, source}
        worker_node("accommodation_worker", task):
          (parallel, same pattern)
        ...
      │
      ▼
      reducer_node:
        1. Combines all worker results
        2. LLM prompt = trip info + worker results
        3. Generates formatted plan (AIMessage)
        4. Resets is_ready_for_planning = False
      │
      ▼
      END → return to user (API picks reducer's plan as last AI message)
```

---

### DynamicPromptMiddleware (`react_agent.py:34`)

The middleware is the key mechanism that makes the agent aware of its current state. It implements `AgentMiddleware.before_agent` which fires before every agent LLM invocation.

```python
class DynamicPromptMiddleware(AgentMiddleware):
    state_schema = AgentState

    def before_agent(self, state, runtime):
        # Read current state
        required = state.get("required_info", {})
        additional = state.get("additional_info", {})

        # Build dynamic context
        known = {k: v for k, v in required.items() if v is not None}
        known["preferences"] = additional.get("preferences", [])
        filled = [f for f in REQUIRED_FIELDS if required.get(f)]
        missing = [f for f in REQUIRED_FIELDS if not required.get(f)]

        # Generate SystemMessage with fresh state
        system_content = f"""
        Currently known: {json.dumps(known)}
        Fields filled: {filled}
        Fields still needed: {missing}
        Your job: gather missing info, one question at a time...
        """

        # Remove old system message to prevent accumulation
        updates = [SystemMessage(content=system_content, id=DYNAMIC_SYSTEM_ID)]
        for m in messages:
            if getattr(m, "id", None) == DYNAMIC_SYSTEM_ID:
                updates.insert(0, RemoveMessage(id=DYNAMIC_SYSTEM_ID))
                break

        return {"messages": updates}
```

This ensures the agent always has an accurate picture of what it knows and what it still needs, without the system prompt growing across turns.

---

### Readiness Detection (`react_agent.py:132`)

The system uses a three-layer guard to determine when to proceed from conversation to planning:

1. **Data Completeness**: All 6 `REQUIRED_FIELDS` must be non-null
   ```python
   REQUIRED_FIELDS = ["start_location", "destination", "start_date",
                      "end_date", "travelers", "budget_range"]
   ```

2. **Agent Not Asking**: The last AI message must not end with `?` (the agent must not be waiting for an answer)

3. **User Confirmed**: The last human message must be a short affirmative (yes, go ahead, sure, proceed, etc.) — prevents triggering when the user is still providing data like "per person" or "Rome"

If the agent explicitly calls the `mark_ready_for_planning` tool (which returns `"READY"`), step 2 and 3 are bypassed.

---

### Web Search Fallback Chain (`nodes.py`)

Each worker attempts to fetch real-time data through a cascade:

```
worker_node(task)
  │
  ├── web_search(task)
  │     │
  │     ├── _tavily_search(query)
  │     │     • Checks TAVILY_API_KEY env var
  │     │     • Calls TavilyClient.search()
  │     │     • Returns formatted snippets or ""
  │     │
  │     ├── _duckduckgo_search(query)  ← fallback
  │     │     • Uses DDGS (free, no key)
  │     │     • Returns formatted snippets or ""
  │     │
  │     └── Returns ""  ← both failed
  │
  ├── If search_results:
  │     Prompt: "Use the search results above as your primary source.
  │              Include specific names, prices, URLs..."
  │
  └── If no results:
        Prompt: "Provide detailed information based on your knowledge."
```

The source (tavily / duckduckgo / training_data) is tracked per worker and exposed in the API response and frontend.

---

### Error Handling

| Failure Point | Behavior |
|---------------|----------|
| **Web search (Tavily/DDG)** | Returns `""`, worker falls back to LLM training data |
| **LLM throttling (Bedrock)** | 3 retries with exponential backoff (1s, 2s, 4s) per worker |
| **Orchestrator LLM failure** | Returns empty worker list, graph ends gracefully |
| **Reducer LLM failure** | Returns "Sorry, I couldn't generate the trip plan." message |
| **Worker LLM failure** | Returns `status: "failed"` with error in result, reducer works with remaining results |

---

## Project Structure

```
.
├── backend/
│   ├── agent/
│   │   ├── graph.py          # Parent graph wiring + run_agent()
│   │   ├── nodes.py          # LLM factory, web search, orchestrator, workers, reducer
│   │   ├── react_agent.py    # Conversational agent, extraction, post-process
│   │   ├── state.py          # AgentState TypedDict + REQUIRED_FIELDS
│   │   ├── subgraphs.py      # Detail-gathering subgraph
│   │   └── subgraphs_old.py  # Legacy (unused)
│   ├── api/
│   │   └── routes.py         # FastAPI router: /api/chat, /api/chat/welcome
│   ├── models/
│   │   └── schemas.py        # Pydantic request/response models
│   ├── main.py               # FastAPI app entry point with CORS + static file serving
│   ├── .env                  # API keys (gitignored)
│   └── .env.example          # Template with all configurable keys
├── frontend/
│   └── app.py                # Streamlit chat UI
├── requirements.txt
└── README.md
```

---

## Frontend (`frontend/app.py`)

Streamlit single-page chat app. Each user message calls `POST /api/chat` with a `session_id` (UUID4, generated once per session).

When the plan comes back:
- **Agent steps expander** (collapsible) shows each worker and its data source:
  - 🦉 `Flights: tavily` — real-time via Tavily
  - 🦆 `Accommodation: duckduckgo` — fallback search
  - 📚 `Itinerary: training_data` — LLM knowledge only
- **Plan display** — rendered via `st.markdown()` in a scrollable container for long responses (>1500 chars)
- **Success banner** — `🎉 Trip plan ready!` appears when `is_complete=True`

---

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat/welcome` | POST | Returns hardcoded welcome greeting |
| `/api/chat` | POST | Process a user message (body: `{message, session_id}`) |
| `/docs` | GET | Swagger UI (auto-generated) |

### `POST /api/chat` Response

```json
{
  "response": "# Your Trip Plan...\n\nDay 1: Arrive in Rome...",
  "is_complete": false,
  "tool_calls": ["mark_ready_for_planning"],
  "worker_calls": ["flights_worker", "accommodation_worker"],
  "worker_sources": [
    "Flights: tavily",
    "Accommodation: duckduckgo",
    "Attractions: training_data"
  ]
}
```

- `response` — the last AI message (either the agent's conversational reply or the reducer's plan)
- `is_complete` — `True` when the orchestrator pipeline ran (always resets to `False` after)
- `tool_calls` — any LLM tool invocations during this turn
- `worker_calls` — worker names from the orchestrator pipeline
- `worker_sources` — per-worker data source (tavily / duckduckgo / training_data)

---

## Setup

### Prerequisites

- Python 3.10+
- [AWS credentials configured](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html) for Bedrock
- [Tavily API key](https://tavily.com) (optional — falls back to DuckDuckGo)

### Installation

```bash
git clone <repo-url>
cd travel-agent
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Configuration

```bash
cp backend/.env.example backend/.env
```

Required:
- **Amazon Bedrock** — `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION` must be set. Default model: `us.anthropic.claude-haiku-4-5-20251001-v1:0`.

Optional:
- **Tavily** — set `TAVILY_API_KEY` for real-time web search. Without it, the system falls back to DuckDuckGo.

### Running

**Backend:**
```bash
uvicorn backend.main:app --reload --port 8000
```

**Frontend** (separate terminal):
```bash
streamlit run frontend/app.py
```

Open [http://localhost:8501](http://localhost:8501) to chat.

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **`create_agent` + `DynamicPromptMiddleware`** over deprecated `create_react_agent` | Middleware injects the current state into the system prompt before each turn without accumulating history |
| **Post-process extraction** instead of LLM tools | Keeps the agent's job simple (just converse). Extraction runs as a cheaper LLM call (temp 0.1) after each turn |
| **Three-layer readiness guard** (data + question + confirmation) | No fragile keyword matching. Triggers only when all fields are filled, the agent isn't waiting for input, and the user explicitly consented |
| **Two-layer graph** (subgraph + parent) | Detail gathering is self-contained and reusable; orchestrator pipeline is separate and only runs on readiness |
| **`ThreadPoolExecutor`** for parallel workers | Simpler than LangGraph `Send` fan-out. Keeps the graph flat and debuggable |
| **Web search fallback chain** (Tavily → DDG → training) | Graceful degradation. No single point of failure for data freshness |
| **LLM retry with exponential backoff** | Bedrock throttling is handled transparently — 3 attempts with 1s/2s/4s waits |
| **`InMemorySaver`** checkpointer | State persists across turns via `thread_id`. No database needed for MVP |
| **Source tracking per worker** | Frontend shows 🦉 Tavily, 🦆 DuckDuckGo, 📚 training data — users know where info comes from |

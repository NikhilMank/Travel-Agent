# Travel Agent — AI Trip Planner

An AI-powered travel agent that plans complete trips through natural conversation. Built with **LangGraph**, **LangChain**, and **Claude Haiku 4.5** on Amazon Bedrock.

## How It Works

The agent uses a **two-layer hierarchical graph**:

1. **Detail Gathering** — converses naturally to collect destination, dates, travelers, budget, and preferences
2. **Orchestrator Pipeline** — parallel workers with real-time web search, then a reducer assembles the plan

```
User Message → Detail Gathering (subgraph) → Orchestrator → Workers (parallel) → Reducer → Complete Plan
```

## Architecture

### Backend (`backend/`)

| Module | File | Role |
|--------|------|------|
| **State** | `agent/state.py` | `AgentState` TypedDict with messages, required_info, is_ready_for_planning |
| **Agent** | `agent/react_agent.py` | `create_agent` with `DynamicPromptMiddleware` that injects current state before each LLM call; extraction LLM for structured info extraction; post-process readiness detection |
| **Subgraph** | `agent/subgraphs.py` | Wraps the agent + post-process into a reusable LangGraph subgraph |
| **Parent Graph** | `agent/graph.py` | Top-level graph wiring detail_gathering → orchestrator → reducer; `InMemorySaver` checkpointer for turn persistence |
| **Nodes** | `agent/nodes.py` | `create_llm` (Bedrock), `orchestrator_node` (generates worker list), `worker_node` (search + LLM), `reducer_node` (assembles plan) |
| **API** | `api/routes.py` | FastAPI endpoints: `POST /api/chat`, `POST /api/chat/welcome` |

### Frontend (`frontend/`)

| File | Role |
|------|------|
| `app.py` | Streamlit chat UI with agent steps expander showing tool and worker source info |

### Plan Generation Flow

1. **Detail Gathering** — agent asks one question at a time, extraction LLM fills `required_info` after each turn
2. **Readiness Detection** — when all 6 required fields filled, agent's last response isn't a question, and user confirmed → `is_ready_for_planning=True`
3. **Orchestrator** — LLM generates a list of specialized workers based on trip details
4. **Workers** (parallel) — each worker runs a web search + LLM to produce flight, hotel, attraction, food, transport, and itinerary data
5. **Reducer** — LLM synthesizes all worker outputs into a complete, coherent trip plan

### Data Sources

Workers fetch real-time data via a fallback chain:
- **Tavily** (primary) — purpose-built LLM search engine, 1000 free calls/month
- **DuckDuckGo** (fallback) — free, no API key required
- **LLM training data** (last resort) — if both search engines fail

## Project Structure

```
.
├── backend/
│   ├── agent/
│   │   ├── graph.py          # Parent graph + run_agent()
│   │   ├── nodes.py          # LLM factory, web search, orchestrator, workers, reducer
│   │   ├── react_agent.py    # Conversational agent, extraction, post-process
│   │   ├── state.py          # AgentState + REQUIRED_FIELDS
│   │   ├── subgraphs.py      # Detail-gathering subgraph
│   │   └── subgraphs_old.py  # Legacy (unused)
│   ├── api/
│   │   └── routes.py         # FastAPI endpoints
│   ├── models/
│   │   └── schemas.py        # Pydantic request/response models
│   ├── main.py               # FastAPI entry point
│   ├── .env                  # API keys (not committed)
│   └── .env.example          # Template for .env
├── frontend/
│   └── app.py                # Streamlit UI
├── requirements.txt
└── README.md
```

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

Copy `.env.example` to `.env` and set your keys:

```bash
cp backend/.env.example backend/.env
```

Required:
- **Amazon Bedrock** — AWS credentials must be configured (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`). The default model is `us.anthropic.claude-haiku-4-5-20251001-v1:0`.

Optional:
- **Tavily** — set `TAVILY_API_KEY` for real-time web search. Without it, the system falls back to DuckDuckGo.

### Running

**Backend:**
```bash
uvicorn backend.main:app --reload --port 8000
```

**Frontend** (in a separate terminal):
```bash
streamlit run frontend/app.py
```

Open `http://localhost:8501` to chat with your travel agent.

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat/welcome` | POST | Returns welcome message |
| `/api/chat` | POST | Send a message (body: `{message, session_id}`) |
| `/docs` | GET | Swagger UI |

`POST /api/chat` response:
```json
{
  "response": "...",
  "is_complete": false,
  "tool_calls": ["mark_ready_for_planning"],
  "worker_calls": ["flights_worker"],
  "worker_sources": ["Flights: tavily"]
}
```

## Key Design Decisions

- **`create_agent` + `DynamicPromptMiddleware`** over deprecated `create_react_agent` — middleware injects the current state into the system prompt before each turn
- **Post-process extraction** instead of LLM tools — keeps the agent's job simple (just converse), extraction runs as a separate cheaper LLM call
- **Data-completeness + guards** for readiness detection — no fragile keyword matching; triggers when all fields are filled, agent isn't asking questions, and user explicitly confirms
- **`ThreadPoolExecutor`** for parallel workers — simpler than LangGraph `Send`, keeps the graph flat
- **`InMemorySaver`** checkpointer — state persists across turns via `thread_id` (mapped from `session_id`)

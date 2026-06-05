# Travel Agent — AI Trip Planner

An AI-powered travel agent that plans complete trips through natural conversation. The agent chats with you to gather your requirements, then orchestrates parallel web-search workers to build a comprehensive, real-time itinerary.

Built with **LangGraph**, **LangChain**, and **Claude Haiku 4.5** on Amazon Bedrock.
Frontend: **React** SPA hosted on **S3 + CloudFront**.
Backend: **FastAPI** + **Mangum** running on **Lambda + API Gateway**.
State: **DynamoDB** for chats, messages, LangGraph checkpoints, and users.
Auth: **JWT** tokens with bcrypt password hashing, per-user chat isolation.

---

## Overview

The system is a two-layer hierarchical state graph. Each user message triggers a full pass through the graph:

1. **Detail Gathering** — a conversational subgraph that collects your trip details naturally, one question at a time
2. **Orchestrator Pipeline** — when all required information is gathered and you confirm, the system dispatches parallel workers to research flights, hotels, attractions, food, and transport via live web search, then assembles everything into a complete trip plan

State persists across turns via a **DynamoDB-backed checkpointer** keyed by a session ID. Messages are stored in DynamoDB and synced on chat switch, new chat, or page close. The frontend displays messages in strict chronological order using timestamp-prefixed message IDs.

---

## How Conversations Flow

A typical interaction looks like this:

1. You say something like *"I want to go to Italy from Germany with 6 people in October"*
2. The agent confirms what it understood and asks for the next missing piece — *"What's your budget range?"*
3. You answer, and the agent moves on to the next question (*"Any preferences for cities or activities?"*)
4. Once everything is gathered, the agent recaps and asks *"Shall I proceed with planning?"*
5. You say *"yes"*, and the system researches and returns a full trip plan

The agent is instructed to ask one question at a time. Ambiguous dates (like 07.10) trigger a clarifying question before proceeding.

---

## Architecture

### Parent Graph

The top-level graph has three nodes: detail gathering, orchestrator, and reducer. After detail gathering, a conditional edge checks a readiness flag. If true, it routes to the orchestrator; otherwise, it returns the agent's response to you.

```
START → Detail Gathering → Orchestrator → Reducer → END
```

### Detail Gathering Subgraph

This is where the conversational agent lives. Each turn follows this path:

1. **Route** — decides whether to show a welcome message or run the agent
2. **React Agent** — the LLM with a dynamic system prompt injected by middleware. The prompt includes exactly what's known, what's missing, and behavioral rules (one question at a time, date clarification, traveler count inference)
3. **Post Process** — runs a separate, lower-temperature LLM call to extract structured fields from the conversation and update the state

This subgraph always returns to END. The parent graph decides whether to proceed to planning.

### Planner Pipeline

When readiness is detected, three stages run sequentially:

1. **Orchestrator** — analyzes your trip details and decides which workers are needed (e.g., flights worker, accommodation worker, attractions worker, food worker, transport worker, itinerary builder)
2. **Workers** — all run in parallel, each performing a web search followed by an LLM call to produce detailed, specific output
3. **Reducer** — takes all worker results and synthesizes them into a coherent, day-by-day trip plan with accommodation recommendations, budget breakdowns, and practical tips

Workers use an exponential backoff retry strategy (up to 3 attempts) to handle API rate limiting gracefully.

---

## Readiness Detection

The system uses a three-layer guard to decide when to switch from conversation to planning:

1. **Data completeness** — all six required fields (departure location, destination, start date, end date, travelers, budget range) must be filled
2. **Agent isn't waiting** — the agent's last message must not end with a question mark, meaning it isn't expecting another answer
3. **You explicitly confirmed** — your last message must be a short affirmative like *"yes"*, *"go ahead"*, or *"proceed"*

If the agent explicitly calls its built-in `mark_ready_for_planning` tool, steps 2 and 3 are bypassed.

---

## Data Sources

Each worker fetches real-time data through a fallback chain:

1. **Tavily** (primary) — a search engine purpose-built for LLM agents, offering 1000 free calls per month
2. **DuckDuckGo** (fallback) — free, no API key needed
3. **LLM training data** (last resort) — if both search engines fail, the worker relies on Claude's built-in knowledge

The data source used by each worker is tracked and displayed in the frontend with icons: 🦉 for Tavily, 🦆 for DuckDuckGo, and 📚 for training data.

---

## Frontend

A **React SPA** built with **Vite**. Key features:

- **Authentication** — email + password login and registration with JWT tokens stored in localStorage
- **Protected routes** — unauthenticated users are redirected to the login page
- **Per-user chat isolation** — each user only sees their own chats
- **Chat interface** — side-by-side layout with chat list and message area
- **Markdown rendering** — assistant messages are rendered with `react-markdown` + `remark-gfm` (tables, lists, headers, code blocks)
- **Dark mode toggle** — sun/moon button in the sidebar, persisted to `localStorage`, respects `prefers-color-scheme`
- **Auto-focus** — input bar is focused on page load and after each message
- **Dirty tracking** — messages are synced to DynamoDB only on chat switch, new chat creation, or page close (`beforeunload` with `keepalive`)
- **Chronological ordering** — messages display in strict order regardless of identical timestamps

---

## Backend API

| Endpoint | Purpose |
|----------|---------|
| `POST /api/auth/register` | Register a new account (returns JWT) |
| `POST /api/auth/login` | Login with email/password (returns JWT) |
| `GET /api/auth/me` | Get current user info (requires auth) |
| `GET /api/chats` | List user's chats, sorted by `updated_at` descending |
| `POST /api/chats` | Create a new chat |
| `GET /api/chats/{id}` | Get a chat with its messages |
| `DELETE /api/chats/{id}` | Delete a chat and its messages |
| `POST /api/chats/{id}/sync` | Sync messages for a chat (overwrites all messages) |
| `PATCH /api/chats/{id}/title` | Rename a chat |
| `POST /api/chat` | Process a user message and return the agent's response or the final plan |

All chat endpoints require a valid JWT token in the `Authorization: Bearer <token>` header. Users can only access their own chats.

All chat and message data is stored in DynamoDB tables (`travel_chats`, `travel_messages`). LangGraph checkpoints use a separate `travel_checkpoints` table.

---

## Project Structure

```
backend/
  agent/
    graph.py                   — Parent graph wiring and graph entry point
    nodes.py                   — LLM factory, web search with fallback, orchestrator, workers, reducer
    react_agent.py             — Conversational agent, extraction LLM, post-process readiness detection
    state.py                   — State schema and required fields list
    subgraphs.py               — Detail-gathering subgraph
    dynamodb_checkpoint.py     — LangGraph checkpointer backed by DynamoDB
  api/
    routes.py                  — FastAPI endpoints (auth + chat)
  database/
    db.py                      — DynamoDB CRUD for chats, messages, users, and sync
  models/
    schemas.py                 — Request and response data models
  auth.py                      — JWT token creation/verification, bcrypt password hashing, get_current_user dependency
  main.py                      — FastAPI app entry point with CORS + Mangum handler

frontend/
  src/
    App.jsx                    — Main React component (sidebar, messages, input, dark mode, routing)
    App.css                    — All styles with CSS variables for theming
    api.js                     — API client functions with auth headers and 401 handling
    contexts/
      AuthContext.jsx           — Auth state management (login, register, logout, token validation)
    pages/
      LoginPage.jsx             — Email/password login form
      RegisterPage.jsx          — Email/password registration form
    components/
      ProtectedRoute.jsx        — Redirects to /login if not authenticated
    main.jsx                   — React entry point
    index.css                  — Global reset styles
  .env                         — VITE_API_URL (localhost for dev, API Gateway for production)
  index.html                   — HTML entry point
  package.json                 — Dependencies (react, react-markdown, react-router-dom, vite)

lambda-package/                — Deployment package for Lambda (built from backend/)
  backend/                     — Source code
  deps/                        — Installed pip packages

travel-agent.zip               — Deployment ZIP for Lambda

template.yaml                  — SAM blueprint (reference only, infra built manually)
requirements.txt               — Python dependencies
```

---

## Setup

### Prerequisites

- Python 3.10+
- Node.js 18+ (for React frontend)
- AWS credentials configured with Bedrock access
- A Tavily API key (optional — falls back to DuckDuckGo)
- DynamoDB tables created in your target region:
  - `AI_Travel_Agent-travel_chats` (partition key: `chat_id`)
  - `AI_Travel_Agent-travel_messages` (partition key: `chat_id`, sort key: `msg_id`)
  - `AI_Travel_Agent-travel-checkpoints` (partition key: `thread_id`, sort key: `checkpoint_id`)
  - `AI_Travel_Agent-travel_users` (partition key: `user_id`, with `email-index` GSI on `email`)

### Local Development

1. **Backend** — create a virtual environment, install dependencies, copy `.env.example` to `.env` and fill in your values (including `JWT_SECRET` for token signing), then start:
   ```bash
   uvicorn backend.main:app --reload --port 8000
   ```

2. **Frontend** — navigate to `frontend/`, install dependencies, set `VITE_API_URL` in `.env` to `http://localhost:8000/api`, then start:
   ```bash
   npm install
   npm run dev
   ```

3. Open `http://localhost:5173` in your browser. Register a new account, log in, and start chatting.

### AWS Deployment

The infrastructure is built manually through the AWS Console (no SAM deploy):

1. **Lambda** — upload `travel-agent.zip` as the function code. Set Python 3.12 runtime, handler as `backend.main.handler`. Configure environment variables matching your `.env` (including `JWT_SECRET`, `DYNAMODB_USERS_TABLE`). Attach the `AWSLambdaBasicExecutionRole` and a custom policy with DynamoDB read/write, Bedrock `InvokeModel`, and access to all four DynamoDB tables + indexes.

2. **API Gateway** — create a REST API, attach the Lambda as a proxy (`ANY /{proxy+}`), deploy to a stage. Enable CORS if needed.

3. **Frontend** — build the React app (`npm run build` in `frontend/` with production API URL), upload `dist/` contents to an S3 bucket with static website hosting enabled.

4. **CloudFront** — create a distribution with your S3 website endpoint as origin. Set default root object to `index.html`. Add custom error responses: 403 → `/index.html` (200) and 404 → `/index.html` (200).

---

## Key Design Decisions

- **DynamoDB over RDS/EFS** — serverless, pay-per-request, no idle cost. Keeps the stack near-zero cost.
- **JWT-based auth with DynamoDB users table** — no Cognito overhead; custom auth keeps control and costs near-zero. Passwords hashed with bcrypt (pinned to 4.2.1 for passlib compatibility).
- **Client-side token storage** — JWT stored in localStorage; `Authorization: Bearer` header sent with every API request. 401 responses redirect to login automatically.
- **Per-user chat isolation** — all chat DB functions accept `user_id`; `list_chats` filters by user (using `scan` + filter for simplicity; GSI can be added at scale).
- **FastAPI + Mangum over raw Lambda handler** — reuses existing routes, validation, and middleware with negligible overhead.
- **Manual console deployment over SAM** — learning-focused approach; SAM template kept as a blueprint reference.
- **Flat deployment ZIP over Lambda Layers** — simpler; single 67MB archive with all deps.
- **Deps in `deps/` subdirectory** — installed packages placed in a `deps/` folder with `sys.path` injection in `main.py`. `botocore`/`boto3` excluded (provided by Lambda runtime).
- **Client-side sync strategy** — messages kept in React state and synced to DynamoDB only on chat switch, new chat, or page close. Minimizes DynamoDB writes.
- **DynamoDB-backed checkpointer** — custom `DynamoDBSaver` uses timestamp-prefixed sort keys for correct checkpoint ordering.
- **Timestamp-prefixed message IDs** — `{created_at}#{i:06d}#{uuid}` format ensures DynamoDB sort key ordering is chronological even when multiple messages share the same timestamp.
- **Custom serialization** — `message_to_dict`/`messages_from_dict` used instead of LangGraph's msgpack format (incompatible with DynamoDB string values).
- **Dynamic middleware over static system prompt** — the agent always knows exactly what's been gathered and what's still needed.
- **Post-process extraction instead of LLM tools** — keeps the agent's job simple (just converse); extraction runs as a separate, cheaper LLM call.
- **Three-layer readiness guard** — triggers only when data is complete, the agent isn't waiting, and you've explicitly consented.
- **Parallel workers with ThreadPoolExecutor** — simpler than LangGraph's fan-out API while achieving the same result.
- **Web search fallback chain** — Tavily, DuckDuckGo, and training data provide three tiers of freshness.
- **Retry with backoff** — Bedrock throttling is handled transparently without user-visible errors.

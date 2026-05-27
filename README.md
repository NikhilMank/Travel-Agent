# Travel Agent — AI Trip Planner

An AI-powered travel agent that plans complete trips through natural conversation. The agent chats with you to gather your requirements, then orchestrates parallel web-search workers to build a comprehensive, real-time itinerary.

Built with **LangGraph**, **LangChain**, and **Claude Haiku 4.5** on Amazon Bedrock.

---

## Overview

The system is a two-layer hierarchical state graph. Each user message triggers a full pass through the graph:

1. **Detail Gathering** — a conversational subgraph that collects your trip details naturally, one question at a time
2. **Orchestrator Pipeline** — when all required information is gathered and you confirm, the system dispatches parallel workers to research flights, hotels, attractions, food, and transport via live web search, then assembles everything into a complete trip plan

State persists across turns using an in-memory checkpointer keyed by a session ID, so the conversation accumulates naturally without any manual state management.

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

A Streamlit single-page chat application. Each message sends a POST request to the backend with the message text and a session ID (generated once per session and stored in Streamlit's session state).

When a plan is returned, the interface shows:

- **An expandable agent steps section** — lists each worker and its data source
- **The plan** — rendered in a scrollable container for long itineraries
- **A success banner** — confirms the trip plan is ready

---

## Backend API

| Endpoint | Purpose |
|----------|---------|
| `POST /api/chat/welcome` | Returns a greeting message for first-time visitors |
| `POST /api/chat` | Processes a user message and returns the agent's response or the final plan |

The chat endpoint accepts a message and session ID, and returns the response text, a completion flag, any tool calls made, worker names, and per-worker data sources.

---

## Project Structure

```
backend/
  agent/
    graph.py          — Parent graph wiring and graph entry point
    nodes.py          — LLM factory, web search with fallback, orchestrator, workers, reducer
    react_agent.py    — Conversational agent, extraction LLM, post-process readiness detection
    state.py          — State schema and required fields list
    subgraphs.py      — Detail-gathering subgraph
  api/
    routes.py         — FastAPI chat endpoints
  models/
    schemas.py        — Request and response data models
  main.py             — FastAPI app entry point with CORS configuration

frontend/
  app.py              — Streamlit chat UI
```

---

## Setup

### Prerequisites

- Python 3.10+
- AWS credentials configured for Bedrock
- A Tavily API key (optional — falls back to DuckDuckGo)

### Installation

Create a virtual environment, install dependencies from requirements.txt, then copy `.env.example` to `.env` and fill in your AWS region and optionally your Tavily key.

### Running

Start the backend with `uvicorn` on port 8000, then start the frontend with `streamlit` on port 8501 in a separate terminal. Open your browser to `http://localhost:8501` to begin.

---

## Key Design Decisions

- **Dynamic middleware** over a static system prompt — the agent always knows exactly what's been gathered and what's still needed, without the prompt growing across turns
- **Post-process extraction** instead of LLM tools — keeps the agent's job simple (just converse); extraction runs as a separate, cheaper LLM call
- **Three-layer readiness guard** — no fragile keyword matching; triggers only when data is complete, the agent isn't waiting, and you've explicitly consented
- **Parallel workers with ThreadPoolExecutor** — simpler than LangGraph's fan-out API while achieving the same result
- **Web search fallback chain** — no single point of failure for real-time data; Tavily, DuckDuckGo, and training data provide three tiers of freshness
- **Retry with backoff** — Bedrock throttling is handled transparently without user-visible errors
- **In-memory checkpointer** — state persists across turns without a database, appropriate for an MVP

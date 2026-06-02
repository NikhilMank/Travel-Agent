"""
FastAPI application entry point for the Travel Agent.

This is the main module that runs the web server.
"""

import sys
import os
from pathlib import Path

# Add deps subdirectory to path if it exists (Lambda deployment structure)
_deps_path = os.path.join(os.path.dirname(__file__), "..", "deps")
if os.path.isdir(_deps_path):
    sys.path.insert(0, _deps_path)

from dotenv import load_dotenv

# Load .env BEFORE any module imports that read env vars
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router


# Create FastAPI app
app = FastAPI(
    title="Travel Agent API",
    description="AI-powered travel agent using LangGraph and LangChain",
    version="1.0.0",
)

# Add CORS middleware to allow frontend to communicate
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the API routes
app.include_router(router, prefix="/api", tags=["chat"])


@app.get("/api-root")
async def root():
    return {
        "message": "Travel Agent API",
        "version": "1.0.0",
        "docs": "/docs",
    }


# Lambda handler
from mangum import Mangum
handler = Mangum(app)
"""
FastAPI application entry point for the Travel Agent.

This is the main module that runs the web server.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router

# Load environment variables from .env file
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)


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
"""
FastAPI application entry point for the Travel Agent.

This is the main module that runs the web server.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

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
    allow_origins=["*"],  # Allow all origins in development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the API routes
app.include_router(router, prefix="/api", tags=["chat"])


# Serve frontend files
# The frontend files should be in the frontend directory at the project root
frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")

if os.path.exists(frontend_path):
    # Mount static files first (for /static/* paths)
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")

    @app.get("/")
    async def serve_frontend():
        """Serve the main frontend HTML file."""
        index_path = os.path.join(frontend_path, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"error": "Frontend not found"}

    @app.get("/index")
    async def serve_frontend_alt():
        """Serve the main frontend HTML file (alternative path)."""
        index_path = os.path.join(frontend_path, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"error": "Frontend not found"}


@app.get("/api-root")
async def root():
    """
    API root endpoint - returns a welcome message.

    Returns:
        Dict with welcome message
    """
    return {
        "message": "Travel Agent API",
        "version": "1.0.0",
        "docs": "/docs",
    }
"""
Models package - Pydantic schemas for the Travel Agent API.
"""

from .schemas import (
    TravelerInfo,
    Message,
    ChatRequest,
    ChatResponse,
)

__all__ = [
    "TravelerInfo",
    "Message",
    "ChatRequest",
    "ChatResponse",
]
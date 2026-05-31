"""
Models package - Pydantic schemas for the Travel Agent API.
"""

from .schemas import (
    TravelerInfo,
    Message,
    ChatRequest,
    ChatResponse,
    ChatMetadata,
    ChatCreateResponse,
    ChatMessageResponse,
    ChatDetailResponse,
)

__all__ = [
    "TravelerInfo",
    "Message",
    "ChatRequest",
    "ChatResponse",
    "ChatMetadata",
    "ChatCreateResponse",
    "ChatMessageResponse",
    "ChatDetailResponse",
]
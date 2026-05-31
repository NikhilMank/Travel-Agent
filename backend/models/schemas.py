from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class ExtractedTripInfo(BaseModel):
    destination: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    travelers: Optional["TravelerInfo"] = None
    budget_range: Optional[str] = None
    preferences: Optional[List[str]] = None


class TravelerInfo(BaseModel):
    num_people: int = 1
    ages: Optional[str] = None


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    conversation_history: List[Message] = []


class ChatResponse(BaseModel):
    response: str
    is_complete: bool = False
    tool_calls: List[str] = []
    worker_calls: List[str] = []
    worker_sources: List[str] = []


class ChatMetadata(BaseModel):
    id: str
    title: str
    updated_at: str


class ChatCreateResponse(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class ChatMessageResponse(BaseModel):
    role: str
    content: str
    created_at: str


class ChatDetailResponse(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    messages: List[ChatMessageResponse]

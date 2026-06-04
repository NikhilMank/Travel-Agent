from fastapi import APIRouter, HTTPException, Depends

from ..models.schemas import (
    ChatRequest,
    ChatResponse,
    ChatCreateResponse,
    ChatDetailResponse,
    ChatMessageResponse,
    ChatMetadata,
    UserCreate,
    UserLogin,
    Token,
    UserResponse,
)
from ..auth import hash_password, verify_password, create_token, get_current_user
from ..agent.graph import compile_agent, run_agent
from ..agent.nodes import extract_text_from_response
from ..database.db import (
    create_chat,
    list_chats,
    get_chat,
    delete_chat,
    update_chat_title,
    sync_messages,
    get_messages,
    create_user,
    get_user_by_email,
)

router = APIRouter()

_agent = None


def get_agent():
    global _agent
    if _agent is None:
        _agent = compile_agent()
    return _agent


@router.post("/chat/welcome")
async def welcome():
    return ChatResponse(
        response="Hi! I'm your travel agent assistant. I'll help you plan your perfect trip. Where would you like to go?",
        is_complete=False,
    )


@router.post("/chats", response_model=ChatCreateResponse)
async def create_new_chat(user: dict = Depends(get_current_user)):
    import uuid
    chat_id = str(uuid.uuid4())
    return create_chat(chat_id, user_id=user["user_id"])


@router.get("/chats", response_model=list[ChatMetadata])
async def get_chat_list(user: dict = Depends(get_current_user)):
    return list_chats(user_id=user["user_id"])


@router.get("/chats/{chat_id}", response_model=ChatDetailResponse)
async def get_chat_detail(chat_id: str, user: dict = Depends(get_current_user)):
    chat = get_chat(chat_id, user_id=user["user_id"])
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    messages = get_messages(chat_id, user_id=user["user_id"])
    return ChatDetailResponse(**chat, messages=[ChatMessageResponse(**m) for m in messages])


@router.post("/chats/{chat_id}/sync")
async def sync_chat_messages(chat_id: str, body: dict, user: dict = Depends(get_current_user)):
    messages = body.get("messages", [])
    chat = get_chat(chat_id, user_id=user["user_id"])
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    if chat["title"] == "New Chat" and messages:
        title = messages[0].get("content", "New Chat")[:50]
        if len(messages[0].get("content", "")) > 50:
            title += "..."
        update_chat_title(chat_id, title, user_id=user["user_id"])
    sync_messages(chat_id, messages, user_id=user["user_id"])
    return {"ok": True}


@router.delete("/chats/{chat_id}")
async def remove_chat(chat_id: str, user: dict = Depends(get_current_user)):
    deleted = delete_chat(chat_id, user_id=user["user_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Chat not found")
    return {"ok": True}


@router.patch("/chats/{chat_id}/title")
async def rename_chat(chat_id: str, body: dict, user: dict = Depends(get_current_user)):
    title = body.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")
    chat = get_chat(chat_id, user_id=user["user_id"])
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    update_chat_title(chat_id, title, user_id=user["user_id"])
    return {"ok": True}


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, user: dict = Depends(get_current_user)):
    try:
        agent = get_agent()

        result = run_agent(agent, request.message, request.session_id)

        messages = result.get("messages", [])
        response_text = ""
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type == "ai":
                response_text = extract_text_from_response(msg)
                break

        if not response_text:
            for msg in reversed(messages):
                response_text = extract_text_from_response(msg)
                if response_text:
                    break

        is_planning = result.get("is_ready_for_planning", False)

        tool_calls = []
        for msg in messages:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls.append(tc.get("name", "unknown"))

        worker_calls = []
        worker_sources = []
        for wr in result.get("worker_results", []):
            w = wr.get("worker", "")
            if w:
                worker_calls.append(w)
                source = wr.get("source", "training_data")
                worker_sources.append(f"{w.replace('_worker', '').replace('_', ' ').title()}: {source}")

        chat_id = request.session_id

        chat_obj = get_chat(chat_id, user_id=user["user_id"])
        if chat_obj and chat_obj["title"] == "New Chat":
            title = request.message[:50]
            if len(request.message) > 50:
                title += "..."
            update_chat_title(chat_id, title, user_id=user["user_id"])

        print(f"Response: {response_text[:100]}...")
        print(f"Tool calls: {tool_calls}")
        print(f"Worker sources: {worker_sources}")

        return ChatResponse(
            response=response_text,
            is_complete=is_planning,
            tool_calls=tool_calls,
            worker_calls=worker_calls,
            worker_sources=worker_sources,
        )

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error in chat endpoint: {error_details}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auth/register", response_model=Token)
async def register(user: UserCreate):
    existing = get_user_by_email(user.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed = hash_password(user.password)
    created = create_user(user.email, hashed)
    token = create_token(created["user_id"])
    return Token(access_token=token)


@router.post("/auth/login", response_model=Token)
async def login(user: UserLogin):
    db_user = get_user_by_email(user.email)
    if not db_user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not verify_password(user.password, db_user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_token(db_user["user_id"])
    return Token(access_token=token)


@router.get("/auth/me", response_model=UserResponse)
async def get_me(user: dict = Depends(get_current_user)):
    return UserResponse(
        user_id=user["user_id"],
        email=user["email"],
        created_at=user.get("created_at", ""),
    )

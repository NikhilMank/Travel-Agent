import streamlit as st
import httpx
from datetime import datetime, timezone

st.set_page_config(page_title="Travel Agent", page_icon="✈️", layout="wide")

st.markdown("""
<style>
    .chat-message p { margin-bottom: 0.25rem; }

    section[data-testid="stSidebar"] { width: 300px !important; }
    section[data-testid="stSidebar"] > div { padding-top: 1.5rem; }
    div[data-testid="stSidebarNav"] { display: none; }

    .sidebar-header {
        display: flex;
        align-items: center;
        gap: 0.6rem;
        padding: 0 0.2rem 1rem;
        border-bottom: 1px solid rgba(128, 128, 128, 0.12);
        margin-bottom: 1rem;
    }
    .sidebar-header span { font-size: 1.4rem; }
    .sidebar-header h2 { margin: 0; font-size: 1.1rem; font-weight: 600; }

    .new-chat-wrap { margin-bottom: 1.25rem; }
    .new-chat-wrap button {
        border: 1px dashed rgba(128, 128, 128, 0.3) !important;
        border-radius: 8px !important;
        background: transparent !important;
        font-weight: 500 !important;
        font-size: 0.85rem !important;
        transition: all 0.15s ease !important;
    }
    .new-chat-wrap button:hover {
        border-color: rgba(128, 128, 128, 0.55) !important;
        background: rgba(128, 128, 128, 0.05) !important;
    }

    .section-label {
        font-size: 0.68rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: rgba(128, 128, 128, 0.45);
        padding: 0 0.2rem;
        margin-bottom: 0.3rem;
        font-weight: 600;
    }

    .chat-title-btn button {
        width: 100% !important;
        padding: 0.5rem 0.75rem !important;
        border: none !important;
        border-radius: 8px !important;
        background: transparent !important;
        cursor: pointer !important;
        text-align: left !important;
        font-family: inherit !important;
        font-size: 0.85rem !important;
        transition: background 0.12s ease !important;
        display: flex !important;
        align-items: center !important;
        justify-content: space-between !important;
    }
    .chat-title-btn button:hover {
        background: rgba(128, 128, 128, 0.06) !important;
    }
    .chat-title-btn button p {
        margin: 0 !important;
        color: var(--text-color, #31333F) !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        flex: 1 !important;
        font-size: 0.85rem !important;
    }

    .chat-row.active .chat-title-btn button {
        background: rgba(70, 130, 200, 0.1) !important;
    }
    .chat-row.active .chat-title-btn button p {
        font-weight: 600 !important;
        color: #1E6BB8 !important;
    }

    .del-btn button {
        background: none !important;
        border: none !important;
        padding: 0.25rem 0.3rem !important;
        font-size: 0.7rem !important;
        color: rgba(128, 128, 128, 0.2) !important;
        cursor: pointer !important;
        transition: color 0.15s ease !important;
        min-width: unset !important;
        width: auto !important;
        border-radius: 4px !important;
    }
    .del-btn button:hover {
        color: rgba(200, 70, 70, 0.7) !important;
        background: rgba(200, 70, 70, 0.08) !important;
    }
</style>
""", unsafe_allow_html=True)

API_BASE = "http://localhost:8000/api"


def api_get(path: str):
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.get(f"{API_BASE}{path}")
            r.raise_for_status()
            return r.json()
    except Exception as e:
        st.error(f"Error: {str(e)}")
        return None


def api_post(path: str, data: dict = None):
    try:
        with httpx.Client(timeout=120.0) as client:
            r = client.post(f"{API_BASE}{path}", json=data or {})
            r.raise_for_status()
            return r.json()
    except Exception as e:
        st.error(f"Error: {str(e)}")
        return None


def api_delete(path: str):
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.delete(f"{API_BASE}{path}")
            r.raise_for_status()
            return r.json()
    except Exception as e:
        st.error(f"Error: {str(e)}")
        return None


def relative_time(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        diff = (now - dt).total_seconds()
        if diff < 60:
            return "now"
        if diff < 3600:
            return f"{int(diff // 60)}m"
        if diff < 86400:
            return f"{int(diff // 3600)}h"
        if diff < 604800:
            return f"{int(diff // 86400)}d"
        return dt.strftime("%b %d")
    except (ValueError, TypeError):
        return ""


def truncate(text: str, length: int = 36) -> str:
    if len(text) <= length:
        return text
    return text[:length].rsplit(" ", 1)[0] + "..."


def refresh_chat_list():
    st.session_state.chat_list = api_get("/chats") or []


def initialize_chat():
    result = api_post("/chats")
    if result:
        st.session_state.session_id = result["id"]
        st.session_state.messages = []
        st.session_state.active_chat_id = result["id"]
        refresh_chat_list()
        return True
    return False


def load_chat(chat_id):
    data = api_get(f"/chats/{chat_id}")
    if data:
        st.session_state.session_id = data["id"]
        st.session_state.messages = [
            {"role": m["role"], "content": m["content"]}
            for m in data.get("messages", [])
        ]
        st.session_state.active_chat_id = data["id"]


def delete_chat(chat_id):
    if api_delete(f"/chats/{chat_id}"):
        if st.session_state.active_chat_id == chat_id:
            st.session_state.session_id = None
            st.session_state.messages = []
            st.session_state.active_chat_id = None
        refresh_chat_list()
        st.rerun()


if "session_id" not in st.session_state:
    st.session_state.session_id = None

if "active_chat_id" not in st.session_state:
    st.session_state.active_chat_id = None

if "messages" not in st.session_state:
    st.session_state.messages = []

if "chat_list" not in st.session_state:
    st.session_state.chat_list = []
    refresh_chat_list()


with st.sidebar:
    st.markdown("""
    <div class="sidebar-header">
        <span>✈️</span>
        <h2>Travel Agent</h2>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="new-chat-wrap">', unsafe_allow_html=True)
    if st.button("+ New Chat", key="new_chat", use_container_width=True, type="secondary"):
        if initialize_chat():
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    if st.session_state.chat_list:
        st.markdown('<div class="section-label">Recent Chats</div>', unsafe_allow_html=True)
        for chat in st.session_state.chat_list:
            chat_id = chat["id"]
            title = truncate(chat["title"])
            time_str = relative_time(chat.get("updated_at", ""))
            is_active = chat_id == st.session_state.active_chat_id

            active_class = " active" if is_active else ""
            st.markdown(f'<div class="chat-row{active_class}">', unsafe_allow_html=True)
            cols = st.columns([7, 1])
            with cols[0]:
                st.markdown('<div class="chat-title-btn">', unsafe_allow_html=True)
                if st.button(f"{title}", key=f"chat_{chat_id}"):
                    load_chat(chat_id)
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)
            with cols[1]:
                st.markdown('<div class="del-btn">', unsafe_allow_html=True)
                if st.button("✕", key=f"del_{chat_id}", help="Delete chat"):
                    delete_chat(chat_id)
                st.markdown("</div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

            if is_active:
                st.markdown(
                    f'<div style="font-size:0.65rem;color:rgba(70,130,200,0.5);padding:0 0.75rem 0.15rem;margin-top:-0.25rem;">{time_str}</div>',
                    unsafe_allow_html=True,
                )

    if st.session_state.session_id is None or not st.session_state.messages:
        if st.session_state.session_id is None:
            initialize_chat()
        if st.session_state.session_id and not st.session_state.messages:
            result = api_post("/chat/welcome")
            if result:
                st.session_state.messages.append(
                    {"role": "assistant", "content": result["response"]}
                )
                st.rerun()


st.title("Travel Agent")
st.markdown("Plan your perfect trip! Tell me about your travel plans.")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(f'<div class="chat-message">{message["content"]}</div>', unsafe_allow_html=True)

if prompt := st.chat_input("What's your travel plan?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = api_post("/chat", {
                "message": prompt,
                "session_id": st.session_state.session_id,
            })

            if response:
                tool_calls = response.get("tool_calls", [])
                worker_calls = response.get("worker_calls", [])
                worker_sources = response.get("worker_sources", [])

                if tool_calls or worker_calls or worker_sources:
                    with st.expander("Agent steps", expanded=False):
                        for tc in tool_calls:
                            st.caption(f"🔧 **{tc}**")
                        for ws in worker_sources:
                            if ": tavily" in ws:
                                icon = "🦉"
                            elif ": duckduckgo" in ws:
                                icon = "🦆"
                            else:
                                icon = "📚"
                            st.caption(f"{icon} **{ws}**")

                content = response.get("response", "")

                if len(content) > 1500:
                    with st.container(height=500):
                        st.markdown(content)
                else:
                    st.markdown(content)

                st.session_state.messages.append(
                    {"role": "assistant", "content": content}
                )

                refresh_chat_list()

                if response.get("is_complete"):
                    st.success("🎉 Trip plan ready!")

import streamlit as st
import httpx
from datetime import datetime, timezone

st.set_page_config(page_title="Travel Agent", page_icon="✈️", layout="wide")



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
            return "just now"
        if diff < 3600:
            return f"{int(diff // 60)}m ago"
        if diff < 86400:
            return f"{int(diff // 3600)}h ago"
        if diff < 604800:
            return f"{int(diff // 86400)}d ago"
        return dt.strftime("%b %d")
    except (ValueError, TypeError):
        return ""


def truncate(text: str, length: int = 32) -> str:
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

if st.session_state.session_id is None:
    if st.session_state.chat_list:
        load_chat(st.session_state.chat_list[0]["id"])
    else:
        initialize_chat()
        resp = api_post("/chat/welcome")
        if resp:
            st.session_state.messages.append(
                {"role": "assistant", "content": resp["response"]}
            )


with st.sidebar:
    st.title("✈️ Travel Agent")

    if st.button("+ New Chat", use_container_width=True, type="secondary"):
        if initialize_chat():
            resp = api_post("/chat/welcome")
            if resp:
                st.session_state.messages.append(
                    {"role": "assistant", "content": resp["response"]}
                )
            st.rerun()

    st.divider()

    if st.session_state.chat_list:
        for chat in st.session_state.chat_list:
            chat_id = chat["id"]
            title = truncate(chat["title"])
            time_str = relative_time(chat.get("updated_at", ""))
            is_active = chat_id == st.session_state.active_chat_id

            label = f"📌 {title}" if is_active else title
            col1, col2 = st.columns([5, 1])
            with col1:
                if st.button(label, key=f"chat_{chat_id}", use_container_width=True):
                    load_chat(chat_id)
                    st.rerun()
            with col2:
                if st.button("✕", key=f"del_{chat_id}", help="Delete chat"):
                    delete_chat(chat_id)

st.title("Travel Agent")
st.markdown("Plan your perfect trip! Tell me about your travel plans.")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

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

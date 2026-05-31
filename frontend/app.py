import streamlit as st
import httpx
from datetime import datetime

st.set_page_config(page_title="Travel Agent", page_icon="✈️", layout="wide")

st.markdown("""
<style>
[data-testid="stChatMessageContent"] p {
    margin-bottom: 0.25rem;
}
</style>
""", unsafe_allow_html=True)

API_BASE = "http://localhost:8000/api"


def api_get(path: str):
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(f"{API_BASE}{path}")
            response.raise_for_status()
            return response.json()
    except Exception as e:
        st.error(f"Error: {str(e)}")
        return None


def api_post(path: str, data: dict = None):
    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(f"{API_BASE}{path}", json=data or {})
            response.raise_for_status()
            return response.json()
    except Exception as e:
        st.error(f"Error: {str(e)}")
        return None


def api_delete(path: str):
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.delete(f"{API_BASE}{path}")
            response.raise_for_status()
            return response.json()
    except Exception as e:
        st.error(f"Error: {str(e)}")
        return None


def refresh_chat_list():
    chats = api_get("/chats")
    st.session_state.chat_list = chats or []


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
    st.title("✈️ Travel Agent")

    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader("Chats")
    with col2:
        if st.button("🆕", help="New Chat"):
            if initialize_chat():
                st.rerun()

    if st.session_state.chat_list:
        st.write("### Recent Chats")
        for chat in st.session_state.chat_list:
            chat_id = chat["id"]
            title = chat["title"]
            try:
                dt = datetime.fromisoformat(chat["updated_at"])
                time_str = dt.strftime("%H:%M")
            except (ValueError, TypeError):
                time_str = ""
            is_active = chat_id == st.session_state.active_chat_id

            cols = st.columns([4, 1])
            with cols[0]:
                if is_active:
                    st.write(f"📌 **{title}**")
                else:
                    if st.button(f"{title} ({time_str})", key=f"chat_{chat_id}"):
                        load_chat(chat_id)
                        st.rerun()
            with cols[1]:
                if st.button("🗑️", key=f"del_{chat_id}", help="Delete chat"):
                    delete_chat(chat_id)

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
                plan_len = len(content)

                if plan_len > 1500:
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

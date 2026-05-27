import streamlit as st
import httpx
import uuid

st.set_page_config(page_title="Travel Agent", page_icon="✈️", layout="wide")

st.markdown("""
<style>
[data-testid="stChatMessageContent"] p {
    margin-bottom: 0.25rem;
}
</style>
""", unsafe_allow_html=True)

API_BASE = "http://localhost:8000/api"

if "messages" not in st.session_state:
    st.session_state.messages = []

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())


def api_post(path: str, data: dict):
    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(f"{API_BASE}{path}", json=data)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        st.error(f"Error: {str(e)}")
        return None


if not st.session_state.messages:
    response = api_post("/chat/welcome", {})
    if response:
        st.session_state.messages.append(
            {"role": "assistant", "content": response["response"]}
        )
    st.rerun()

st.title("✈️ Travel Agent")
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

                if response.get("is_complete"):
                    st.success("🎉 Trip plan ready!")


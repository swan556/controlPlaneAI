import streamlit as st
import requests
import random
import threading
from streamlit.runtime.scriptrunner import add_script_run_ctx

import uuid

# --- Page Config ---
st.set_page_config(
    page_title="ControlPlane AI Chat",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())


# --- Custom Styling ---
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    .chat-header {
        background: rgba(14, 17, 23, 0.8);
        backdrop-filter: blur(10px);
        padding: 1.5rem;
        border-radius: 15px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        text-align: center;
        margin-bottom: 2rem;
    }
    .gradient-text {
        background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 800;
        font-size: 2.5rem;
    }
    .subtext { color: #888; font-size: 1.1rem; margin-top: 0.5rem; }
    .status-pill {
        display: inline-block;
        padding: 0.2rem 0.8rem;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: bold;
        background: #ff4b4b;
        color: white;
        margin-bottom: 1rem;
    }
    .card-header-raw {
        padding: 0.6rem 1rem;
        border-radius: 10px 10px 0 0;
        background: rgba(255, 75, 75, 0.15);
        border: 1px solid rgba(255, 75, 75, 0.3);
        border-bottom: none;
        font-weight: 700;
        color: #ff6b6b;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    .card-header-cp {
        padding: 0.6rem 1rem;
        border-radius: 10px 10px 0 0;
        background: rgba(0, 242, 254, 0.15);
        border: 1px solid rgba(0, 242, 254, 0.3);
        border-bottom: none;
        font-weight: 700;
        color: #00f2fe;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    .stream-card {
        padding: 1.2rem;
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 0 0 10px 10px;
        min-height: 180px;
        line-height: 1.6;
        font-size: 0.95rem;
    }
    blockquote {
        border-left: 4px solid #00f2fe !important;
        background: rgba(0, 242, 254, 0.07) !important;
        padding: 0.8rem 1rem !important;
        border-radius: 0 8px 8px 0 !important;
        margin: 1rem 0 !important;
    }
</style>
""", unsafe_allow_html=True)

PROXY_API_URL = "http://127.0.0.1:8000"

st.sidebar.title("Modes")
mode = st.sidebar.radio("Select Interface:", ["Standard Chat", "Testing Mode (Side-by-Side)"])

st.markdown("""
<div class="chat-header">
    <div class="gradient-text">ControlPlane Engine</div>
    <div class="subtext">Real-time Mistral Agent Evaluation & Security Streaming</div>
</div>
""", unsafe_allow_html=True)

# --- Standard Chat Mode ---
if mode == "Standard Chat":
    if "std_messages" not in st.session_state:
        st.session_state.std_messages = []

    for message in st.session_state.std_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    def get_stream_generator(prompt: str):
        try:
            response = requests.post(f"{PROXY_API_URL}/stream-check", json={"prompt": prompt, "session_id": st.session_state.session_id}, stream=True, timeout=10)
            response.raise_for_status()
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    yield chunk.decode("utf-8")
        except requests.exceptions.RequestException as e:
            yield f"\n\n**Error:** `{str(e)}`"

    if prompt := st.chat_input("Ask the Mistral agent anything..."):
        with st.chat_message("user"):
            st.markdown(prompt)
        st.session_state.std_messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("assistant"):
            full_response = st.write_stream(get_stream_generator(prompt))
        st.session_state.std_messages.append({"role": "assistant", "content": full_response})


# --- Testing Mode (Side-by-Side) ---
elif mode == "Testing Mode (Side-by-Side)":
    st.markdown("### 🧪 Concurrent Evaluation Arena")
    # We won't keep a long running history here to keep the UI clean, just the current turn.
    if prompt := st.chat_input("Test a prompt (e.g. What is Sarah Jenkins' salary?)"):
        
        actual_prompt = prompt
        
        with st.chat_message("user"):
            st.markdown(prompt)

        col1, col2 = st.columns(2)
        with col1:
            st.markdown('<div class="card-header-raw">Mistral Model (Raw & Unguarded)</div>', unsafe_allow_html=True)
            raw_container = st.empty()
            
        with col2:
            st.markdown('<div class="card-header-cp">ControlPlane AI (Active Defense & Self-Healing)</div>', unsafe_allow_html=True)
            cp_container = st.empty()

        st.markdown("---")
        action_container = st.empty()

        # Single stream reader parsing JSON lines for exact synchronized evaluation
        def stream_dual(endpoint, final_prompt, raw_cnt, cp_cnt, action_cnt):
            try:
                import json
                resp = requests.post(endpoint, json={"prompt": final_prompt, "session_id": st.session_state.session_id}, stream=True, timeout=15)
                raw_text = ""
                cp_text = ""
                for line in resp.iter_lines():
                    if line:
                        try:
                            data = json.loads(line.decode('utf-8'))
                            if "raw" in data:
                                raw_text += data["raw"]
                                raw_cnt.markdown(f'<div class="stream-card">{raw_text}▌</div>', unsafe_allow_html=True)
                            if "cp" in data:
                                cp_text += data["cp"]
                                cp_cnt.markdown(cp_text + "▌")
                            if "action" in data:
                                action = data["action"]
                                if action == "BLOCK":
                                    action_cnt.error(f"**Action Taken: BLOCK** — Connection Severed | Attack/Leakage Mitigated")
                                elif action == "EDIT":
                                    action_cnt.warning(f"**Action Taken: EDIT** — Hallucinated claim replaced with Company Ground Truth")
                                elif action == "FLAG":
                                    action_cnt.warning(f"**Action Taken: FLAG** — Counterfactual Demographic Bias Detected | Logged for Review")
                                else:
                                    action_cnt.success(f"**Action Taken: ALLOW** — Output satisfies all performance, safety, and governance thresholds")
                        except json.JSONDecodeError:
                            pass
                raw_cnt.markdown(f'<div class="stream-card">{raw_text}</div>', unsafe_allow_html=True)
                cp_cnt.markdown(cp_text)
            except Exception as e:
                raw_cnt.error(f"Stream Error: {str(e)}")
                cp_cnt.error(f"Stream Error: {str(e)}")

        stream_dual(f"{PROXY_API_URL}/stream-dual", actual_prompt, raw_container, cp_container, action_container)

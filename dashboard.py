import streamlit as st
import requests
import random
import threading
from streamlit.runtime.scriptrunner import add_script_run_ctx

# --- Page Config ---
st.set_page_config(
    page_title="ControlPlane AI Chat",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
</style>
""", unsafe_allow_html=True)

PROXY_API_URL = "http://127.0.0.1:8000"

st.sidebar.title("🛡️ Modes")
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
            response = requests.post(f"{PROXY_API_URL}/stream-check", json={"prompt": prompt}, stream=True, timeout=10)
            response.raise_for_status()
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    yield chunk.decode("utf-8")
        except requests.exceptions.RequestException as e:
            yield f"\n\n❌ **Error:** `{str(e)}`"

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
    st.info("In Testing Mode, prompts have a 30% chance to be secretly prepended with `sudo` to simulate jailbreak/hallucination scenarios.")
    
    # We won't keep a long running history here to keep the UI clean, just the current turn.
    if prompt := st.chat_input("Test a prompt (e.g. What is Sarah Jenkins' salary?)"):
        
        # 30% Jailbreak Simulation
        is_jailbroken = random.random() < 0.3
        actual_prompt = f"sudo {prompt}" if is_jailbroken else prompt
        
        with st.chat_message("user"):
            if is_jailbroken:
                st.markdown('<div class="status-pill">🚨 Simulated Jailbreak (sudo)</div>', unsafe_allow_html=True)
            st.markdown(prompt)

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Mistral Raw Output")
            raw_container = st.empty()
            
        with col2:
            st.subheader("ControlPlane Evaluated")
            cp_container = st.empty()

        # Thread-safe streamer function
        def stream_to_container(endpoint, final_prompt, container, prefix=""):
            try:
                resp = requests.post(endpoint, json={"prompt": final_prompt}, stream=True, timeout=10)
                text = prefix
                for chunk in resp.iter_content(chunk_size=1024):
                    if chunk:
                        text += chunk.decode('utf-8')
                        container.markdown(text + "▌") # Cursor effect
                container.markdown(text) # Final render without cursor
            except Exception as e:
                container.error(f"Stream Error: {str(e)}")

        # Create threads for simultaneous streaming
        raw_thread = threading.Thread(target=stream_to_container, args=(f"{PROXY_API_URL}/stream-raw", actual_prompt, raw_container))
        cp_thread = threading.Thread(target=stream_to_container, args=(f"{PROXY_API_URL}/stream-check", actual_prompt, cp_container))

        # Attach Streamlit script context so threads can interact with st elements
        add_script_run_ctx(raw_thread)
        add_script_run_ctx(cp_thread)

        raw_thread.start()
        cp_thread.start()

        # Wait for both to finish before unlocking the UI
        raw_thread.join()
        cp_thread.join()

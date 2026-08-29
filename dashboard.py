import streamlit as st
import requests
import json

# --- Page Config ---
st.set_page_config(
    page_title="ControlPlane AI Chat",
    page_icon="🛡️",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# --- Custom Styling ---
st.markdown("""
<style>
    /* Dark glassmorphism header */
    .stApp {
        background-color: #0e1117;
    }
    
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
    
    .subtext {
        color: #888;
        font-size: 1.1rem;
        margin-top: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="chat-header">
    <div class="gradient-text">ControlPlane Engine</div>
    <div class="subtext">Real-time Mistral Agent Evaluation & Security Streaming</div>
</div>
""", unsafe_allow_html=True)

PROXY_API_URL = "http://127.0.0.1:8000"

# --- Session State for Chat History ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

def get_stream_generator(prompt: str):
    """Generator that yields chunks from the requests stream."""
    try:
        # We use stream-check endpoint
        response = requests.post(
            f"{PROXY_API_URL}/stream-check",
            json={"prompt": prompt},
            stream=True,
            timeout=10
        )
        response.raise_for_status()
        
        # Iterate over the raw content. The server yields space-separated sentences
        # so iter_content or iter_lines both work. We'll read chunk by chunk.
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                # Decode chunk to string
                text = chunk.decode("utf-8")
                yield text
                
    except requests.exceptions.RequestException as e:
        yield f"\n\n❌ **Error connecting to ControlPlane Proxy:** `{str(e)}`"

# --- Chat Input ---
if prompt := st.chat_input("Ask the Mistral agent anything... (e.g. Can I work from a cafe?)"):
    # Display user message in chat message container
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Display assistant response in chat message container
    with st.chat_message("assistant"):
        # We use st.write_stream to yield the chunks dynamically
        # It handles the typewriter effect nicely!
        full_response = st.write_stream(get_stream_generator(prompt))
        
    # Add assistant response to chat history
    st.session_state.messages.append({"role": "assistant", "content": full_response})

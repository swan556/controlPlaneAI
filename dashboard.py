import streamlit as st
import requests
import json
import uuid

# --- Page Config ---
st.set_page_config(
    page_title="Northstar Systems - Customer Portal",
    page_icon="N",
    layout="wide",
    initial_sidebar_state="expanded"
)

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

PROXY_API_URL = "http://127.0.0.1:8000"

# --- Global CSS ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

    /* ── Global ───────────────────────────────────────────── */
    .stApp {
        background: linear-gradient(160deg, #09090b 0%, #121212 40%, #18181b 100%);
        font-family: 'Inter', sans-serif;
    }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #111111 0%, #0a0a0a 100%);
        border-right: 1px solid rgba(255, 255, 255, 0.05);
    }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
    [data-testid="stSidebar"] .stRadio label {
        color: #94a3b8 !important;
    }

    /* ── Northstar Navbar ─────────────────────────────────── */
    .ns-navbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0.8rem 1.5rem;
        background: rgba(15, 15, 15, 0.85);
        backdrop-filter: blur(16px);
        border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 12px;
        margin-bottom: 1.5rem;
    }
    .ns-logo {
        display: flex;
        align-items: center;
        gap: 0.6rem;
    }
    .ns-logo-icon {
        width: 32px; height: 32px;
        background: linear-gradient(135deg, #555555, #333333);
        border-radius: 8px;
        display: flex; align-items: center; justify-content: center;
        font-size: 1.1rem;
    }
    .ns-logo-text {
        font-weight: 800; font-size: 1.2rem;
        background: linear-gradient(90deg, #999999, #cccccc);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .ns-nav-links {
        display: flex; gap: 1.8rem; align-items: center;
    }
    .ns-nav-links a {
        color: #64748b; text-decoration: none; font-size: 0.85rem;
        font-weight: 500; transition: color 0.2s;
    }
    .ns-nav-links a:hover { color: #e2e8f0; }
    .ns-nav-links a.active { color: #ffffff; font-weight: 700; }
    .ns-user-badge {
        display: flex; align-items: center; gap: 0.5rem;
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 20px;
        padding: 0.3rem 0.8rem 0.3rem 0.4rem;
        font-size: 0.8rem; color: #94a3b8;
    }
    .ns-user-avatar {
        width: 24px; height: 24px;
        background: linear-gradient(135deg, #555555, #333333);
        border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-size: 0.7rem; color: white; font-weight: 700;
    }

    /* ── Metric Cards ─────────────────────────────────────── */
    .metric-card {
        background: rgba(255,255,255,0.01);
        border: 1px solid rgba(255,255,255,0.03);
        border-radius: 14px;
        padding: 1.2rem 1.4rem;
        transition: border-color 0.3s, transform 0.2s;
    }
    .metric-card:hover {
        border-color: rgba(255, 255, 255, 0.08);
        transform: translateY(-2px);
    }
    .metric-label {
        font-size: 0.75rem; color: #64748b;
        font-weight: 600; text-transform: uppercase;
        letter-spacing: 0.05em; margin-bottom: 0.3rem;
    }
    .metric-value {
        font-size: 1.8rem; font-weight: 800; color: #e2e8f0;
    }
    .metric-delta {
        font-size: 0.75rem; font-weight: 600; margin-top: 0.2rem;
    }
    .metric-delta.up { color: #888888; }
    .metric-delta.down { color: #666666; }

    /* ── Section Headers ──────────────────────────────────── */
    .section-title {
        font-size: 1.05rem; font-weight: 700; color: #e2e8f0;
        margin-bottom: 0.8rem; margin-top: 1.2rem;
        display: flex; align-items: center; gap: 0.5rem;
    }

    /* ── Status Table ─────────────────────────────────────── */
    .status-table {
        width: 100%;
        border-collapse: separate;
        border-spacing: 0;
        background: rgba(255,255,255,0.01);
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid rgba(255,255,255,0.03);
    }
    .status-table th {
        background: rgba(255, 255, 255, 0.03);
        color: #64748b;
        font-size: 0.72rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        padding: 0.7rem 1rem;
        text-align: left;
        border-bottom: 1px solid rgba(255,255,255,0.02);
    }
    .status-table td {
        padding: 0.65rem 1rem;
        font-size: 0.85rem;
        color: #cbd5e1;
        border-bottom: 1px solid rgba(255,255,255,0.03);
    }
    .status-table tr:last-child td { border-bottom: none; }
    .status-pill-green {
        display: inline-block; padding: 0.15rem 0.6rem;
        border-radius: 10px; font-size: 0.72rem; font-weight: 600;
        background: rgba(255, 255, 255, 0.05); color: #a3a3a3;
        border: 1px solid rgba(255, 255, 255, 0.10);
    }
    .status-pill-yellow {
        display: inline-block; padding: 0.15rem 0.6rem;
        border-radius: 10px; font-size: 0.72rem; font-weight: 600;
        background: rgba(255, 255, 255, 0.03); color: #888888;
        border: 1px solid rgba(255, 255, 255, 0.08);
    }

    /* ── Activity Feed ────────────────────────────────────── */
    .activity-item {
        display: flex; align-items: flex-start; gap: 0.7rem;
        padding: 0.6rem 0;
        border-bottom: 1px solid rgba(255,255,255,0.04);
    }
    .activity-item:last-child { border-bottom: none; }
    .activity-dot {
        width: 8px; height: 8px;
        border-radius: 50%;
        margin-top: 0.35rem;
        flex-shrink: 0;
    }
    .activity-dot.blue { background: #555555; }
    .activity-dot.green { background: #777777; }
    .activity-dot.amber { background: #666666; }
    .activity-dot.purple { background: #444444; }
    .activity-text {
        font-size: 0.82rem; color: #94a3b8; line-height: 1.4;
    }
    .activity-text strong { color: #cbd5e1; }
    .activity-time {
        font-size: 0.7rem; color: #475569; margin-top: 0.1rem;
    }

    /* ── Chat Panel (right side) ──────────────────────────── */
    .chat-panel-header {
        display: flex; align-items: center; justify-content: space-between;
        padding: 0.9rem 1.2rem;
        background: rgba(15, 15, 18, 0.9);
        border: 1px solid rgba(168, 85, 247, 0.6); /* Vibrant Neon Purple */
        border-bottom: none;
        border-radius: 12px 12px 0 0;
        box-shadow: 0 -10px 30px -10px rgba(168, 85, 247, 0.25);
    }
    .chat-panel-title {
        display: flex; align-items: center; gap: 0.5rem;
        font-size: 0.9rem; font-weight: 800; color: #ffffff;
        letter-spacing: 0.02em;
    }
    .chat-panel-badge {
        font-size: 0.62rem; font-weight: 700;
        background: linear-gradient(135deg, #38bdf8, #818cf8);
        color: white;
        padding: 0.15rem 0.5rem;
        border-radius: 8px;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    /* We still define chat-panel-body style even though it's wrapped in st.container now, 
       just to keep quick-actions styled, but the main glowing effect is applied via st.container later */
    .cp-shield-badge {
        display: flex; align-items: center; gap: 0.35rem;
        font-size: 0.65rem; color: #10b981; /* Vibrant Emerald Green */
        background: rgba(16, 185, 129, 0.1);
        border: 1px solid rgba(16, 185, 129, 0.4);
        border-radius: 8px;
        padding: 0.2rem 0.5rem;
        font-weight: 700;
        box-shadow: 0 0 10px rgba(16, 185, 129, 0.25);
    }

    /* ── Chat message overrides inside panel ───────────────── */
    blockquote {
        border-left: 4px solid #a855f7 !important; /* Neon Purple */
        background: rgba(168, 85, 247, 0.08) !important;
        padding: 0.8rem 1rem !important;
        border-radius: 0 8px 8px 0 !important;
        margin: 0.8rem 0 !important;
    }

    /* ── Quick Action Buttons ──────────────────────────────── */
    .quick-actions {
        display: flex; gap: 0.5rem; flex-wrap: wrap;
        margin: 0.5rem 0 0.8rem 0;
    }
    .qa-btn {
        display: inline-block;
        padding: 0.35rem 0.75rem;
        font-size: 0.75rem;
        color: #94a3b8;
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 8px;
        cursor: pointer;
        transition: all 0.2s;
    }
    .qa-btn:hover {
        background: rgba(56, 189, 248, 0.08);
        border-color: rgba(56, 189, 248, 0.2);
        color: #38bdf8;
    }

    /* ── Testing mode cards (preserved) ───────────────────── */
    .card-header-good {
        background: rgba(16, 185, 129, 0.15); /* Emerald green for good */
        border: 1px solid rgba(16, 185, 129, 0.3);
        color: #10b981;
        padding: 0.6rem 1rem;
        font-weight: 700; font-size: 0.85rem;
        border-radius: 8px 8px 0 0;
        text-align: center;
        text-transform: uppercase; letter-spacing: 0.05em;
    }
    .card-header-raw {
        padding: 0.6rem 1rem;
        border-radius: 10px 10px 0 0;
        background: rgba(255, 75, 75, 0.15);
        border: 1px solid rgba(255, 75, 75, 0.3);
        border-bottom: none;
        font-weight: 700; color: #ff6b6b;
        display: flex; align-items: center; gap: 0.5rem;
    }
    .card-header-cp {
        padding: 0.6rem 1rem;
        border-radius: 10px 10px 0 0;
        background: rgba(0, 242, 254, 0.15);
        border: 1px solid rgba(0, 242, 254, 0.3);
        border-bottom: none;
        font-weight: 700; color: #00f2fe;
        display: flex; align-items: center; gap: 0.5rem;
    }
    .stream-card {
        padding: 1.2rem;
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 0 0 10px 10px;
        min-height: 180px; line-height: 1.6; font-size: 0.95rem;
    }
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
#  SIDEBAR
# ═══════════════════════════════════════════════════════════════

# Sidebar branding
st.sidebar.markdown("""
<div style="display:flex;align-items:center;gap:0.7rem;margin-bottom:1.2rem;">
    <div style="width:28px;height:28px;background:linear-gradient(135deg,#555,#333);border-radius:7px;display:flex;align-items:center;justify-content:center;font-size:0.9rem;color:#ccc;">N</div>
    <span style="font-weight:800;font-size:1.05rem;background:linear-gradient(90deg,#999,#ccc);-webkit-background-clip:text;-webkit-text-fill-color:transparent;">Northstar Systems</span>
</div>
""", unsafe_allow_html=True)

mode = st.sidebar.radio(
    "Navigate",
    ["Dashboard", "Testing Arena"],
    label_visibility="collapsed"
)

# Sidebar info block
st.sidebar.markdown("---")
st.sidebar.markdown("""
<div style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.05);border-radius:10px;padding:0.8rem;margin-top:0.5rem;">
    <div style="font-size:0.72rem;color:#64748b;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.4rem;">Current Plan</div>
    <div style="font-size:0.95rem;color:#e2e8f0;font-weight:700;">Business</div>
    <div style="font-size:0.72rem;color:#64748b;margin-top:0.2rem;">25 users · 1 TB storage</div>
</div>
""", unsafe_allow_html=True)

st.sidebar.markdown("""
<div style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.05);border-radius:10px;padding:0.8rem;margin-top:0.6rem;">
    <div style="font-size:0.72rem;color:#64748b;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.4rem;">Assistant</div>
    <div style="display:flex;align-items:center;gap:0.4rem;">
        <div style="width:7px;height:7px;background:#64748b;border-radius:50%;"></div>
        <span style="font-size:0.82rem;color:#64748b;font-weight:600;">Protected by ControlPlane</span>
    </div>
    <div style="font-size:0.70rem;color:#64748b;margin-top:0.2rem;">Real-time guardrails active</div>
</div>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
#  DASHBOARD MODE
# ═══════════════════════════════════════════════════════════════

if mode == "Dashboard":

    # ── Navbar ──
    st.markdown("""
    <div class="ns-navbar">
        <div class="ns-logo">
            <div class="ns-logo-icon">N</div>
            <div class="ns-logo-text">Northstar Systems</div>
        </div>
        <div class="ns-nav-links">
            <a href="#" class="active">Dashboard</a>
            <a href="#">Products</a>
            <a href="#">Billing</a>
            <a href="#">Support</a>
            <a href="#">Docs</a>
        </div>
        <div class="ns-user-badge">
            <div class="ns-user-avatar">JD</div>
            Jane Doe
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Main Layout: Dashboard (left 60%) | Chat (right 40%) ──
    dash_col, chat_col = st.columns([3, 2], gap="large")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  LEFT: Simulated Northstar Dashboard
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    with dash_col:
        # Metric row
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.markdown("""
            <div class="metric-card">
                <div class="metric-label">Active VMs</div>
                <div class="metric-value">12</div>
                <div class="metric-delta up">↑ 2 this week</div>
            </div>
            """, unsafe_allow_html=True)
        with m2:
            st.markdown("""
            <div class="metric-card">
                <div class="metric-label">API Requests (24h)</div>
                <div class="metric-value">847K</div>
                <div class="metric-delta up">↑ 12% vs yesterday</div>
            </div>
            """, unsafe_allow_html=True)
        with m3:
            st.markdown("""
            <div class="metric-card">
                <div class="metric-label">Storage Used</div>
                <div class="metric-value">684 GB</div>
                <div class="metric-delta down">68% of limit</div>
            </div>
            """, unsafe_allow_html=True)
        with m4:
            st.markdown("""
            <div class="metric-card">
                <div class="metric-label">Uptime (30d)</div>
                <div class="metric-value">99.97%</div>
                <div class="metric-delta up">Above SLA</div>
            </div>
            """, unsafe_allow_html=True)

        # ── Service Status ──
        st.markdown('<div class="section-title">Service Status</div>', unsafe_allow_html=True)
        st.markdown("""
        <table class="status-table">
            <thead>
                <tr><th>Service</th><th>Region</th><th>Status</th><th>Latency</th></tr>
            </thead>
            <tbody>
                <tr><td>Northstar Cloud</td><td>US East</td><td><span class="status-pill-green">Operational</span></td><td>12 ms</td></tr>
                <tr><td>Northstar Cloud</td><td>Europe West</td><td><span class="status-pill-green">Operational</span></td><td>34 ms</td></tr>
                <tr><td>Northstar Edge</td><td>US West</td><td><span class="status-pill-green">Operational</span></td><td>8 ms</td></tr>
                <tr><td>Northstar Monitor</td><td>Global</td><td><span class="status-pill-green">Operational</span></td><td>18 ms</td></tr>
                <tr><td>Northstar API</td><td>Global</td><td><span class="status-pill-green">Operational</span></td><td>22 ms</td></tr>
                <tr><td>Northstar Backup</td><td>US East</td><td><span class="status-pill-yellow">Maintenance</span></td><td>-</td></tr>
            </tbody>
        </table>
        """, unsafe_allow_html=True)

        # ── Recent Activity ──
        st.markdown('<div class="section-title" style="margin-top:1.5rem;">Recent Activity</div>', unsafe_allow_html=True)
        st.markdown("""
        <div style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:12px;padding:0.8rem 1rem;">
            <div class="activity-item">
                <div class="activity-dot blue"></div>
                <div>
                    <div class="activity-text"><strong>VM us-east-prod-04</strong> scaled to 8 vCPU / 32 GB</div>
                    <div class="activity-time">2 minutes ago · by Jane Doe</div>
                </div>
            </div>
            <div class="activity-item">
                <div class="activity-dot green"></div>
                <div>
                    <div class="activity-text"><strong>Backup completed</strong> for storage volume vol-0291</div>
                    <div class="activity-time">18 minutes ago · automated</div>
                </div>
            </div>
            <div class="activity-item">
                <div class="activity-dot amber"></div>
                <div>
                    <div class="activity-text"><strong>Alert resolved:</strong> CPU usage on us-west-edge-02 returned to normal</div>
                    <div class="activity-time">43 minutes ago · Northstar Monitor</div>
                </div>
            </div>
            <div class="activity-item">
                <div class="activity-dot purple"></div>
                <div>
                    <div class="activity-text"><strong>API key rotated</strong> for service account svc-deploy-ci</div>
                    <div class="activity-time">1 hour ago · by Mike Chen</div>
                </div>
            </div>
            <div class="activity-item">
                <div class="activity-dot blue"></div>
                <div>
                    <div class="activity-text"><strong>New VM deployed:</strong> eu-west-staging-07 (Debian 12, 4 vCPU)</div>
                    <div class="activity-time">2 hours ago · by Jane Doe</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  RIGHT: ControlPlane-Protected Chatbot
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    with chat_col:
        # Chat panel header (Unified with the container)
        st.markdown("""
        <div class="chat-panel-header">
            <div class="chat-panel-title">
                Northstar Assistant
            </div>
            <div class="cp-shield-badge">
                ControlPlane Active
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Style the Streamlit container itself to have glowing border
        st.markdown("""
        <style>
        [data-testid="stVerticalBlockBorderWrapper"]:has(.stChatInput) {
            border: 1px solid rgba(168, 85, 247, 0.6) !important;
            border-top: none !important;
            border-radius: 0 0 12px 12px !important;
            box-shadow: 0 10px 30px -5px rgba(168, 85, 247, 0.25) !important;
            background: rgba(15, 15, 18, 0.9) !important;
        }
        </style>
        """, unsafe_allow_html=True)

        # Chat body container using Streamlit's native scrollable container
        chat_container = st.container(height=450, border=True)

        # Initialize chat state
        if "ns_messages" not in st.session_state:
            st.session_state.ns_messages = []

        # Render chat history
        with chat_container:
            for message in st.session_state.ns_messages:
                avatar = None
                with st.chat_message(message["role"], avatar=avatar):
                    st.markdown(message["content"])

        # Agent IDs
        GOOD_AGENT = "ag_01a05e48d29a7723abdb5978b5d22dbd"
        HALLUCINATING_AGENT = "ag_01a048474f7872db90a903ea31477b48"

        def pick_agent():
            """70% good agent, 30% hallucinating agent."""
            import random
            return HALLUCINATING_AGENT if random.random() < 0.30 else GOOD_AGENT

        # Stream generator that cleans up ControlPlane alert messages
        def get_ns_stream(prompt: str):
            agent_id = pick_agent()
            agent_label = "Good Agent" if agent_id == GOOD_AGENT else "Hallucinating Agent"
            yield f"`[Debug: Routed to {agent_label}]`\n\n"
            
            try:
                response = requests.post(
                    f"{PROXY_API_URL}/stream-check",
                    json={
                        "prompt": prompt,
                        "session_id": st.session_state.session_id,
                        "agent_id": agent_id
                    },
                    stream=True, timeout=30
                )
                response.raise_for_status()

                buffer = ""
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        text = chunk.decode("utf-8")
                        buffer += text

                        # ControlPlane Alert handling
                        if "⚠️ [ControlPlane" in text:
                            # We intercepted an alert mid-stream.
                            # Since we already streamed previous safe sentences to the user,
                            # appending a generic "I can't help you" looks weird.
                            # Instead, we just neatly indicate the response was halted.
                            
                            # If it's a pre-flight block (nothing was streamed yet):
                            if buffer.strip().startswith("⚠️ [ControlPlane"):
                                if "Connection severed" in buffer:
                                    yield "🔒 **[System Lock]** Your session has been disabled due to repeated security violations (Cumulative Risk Threshold Exceeded). Please refresh the page to start a new session."
                                else:
                                    yield "I'm sorry, I cannot fulfill this request due to Northstar's security and privacy policies. Please contact support if you need further assistance."
                            else:
                                # It's an in-flight block (partial response already streamed)
                                yield "\n\n*(Response halted by Northstar Security Guardrails)*"
                            return
                            
                        # Normal token — yield as-is
                        yield text

            except requests.exceptions.RequestException as e:
                yield "I'm having trouble connecting right now. Please try again in a moment."

        # Chat input
        if prompt := st.chat_input("Ask about Northstar products, billing, support..."):
            with chat_container:
                with st.chat_message("user"):
                    st.markdown(prompt)
                st.session_state.ns_messages.append({"role": "user", "content": prompt})
    
                with st.chat_message("assistant"):
                    full_response = st.write_stream(get_ns_stream(prompt))
                st.session_state.ns_messages.append({"role": "assistant", "content": full_response})


# ═══════════════════════════════════════════════════════════════
#  TESTING ARENA MODE (untouched from original)
# ═══════════════════════════════════════════════════════════════

elif mode == "Testing Arena":

    st.markdown("""
    <div style="text-align:center;padding:1rem;margin-bottom:1rem;">
        <div style="font-size:2rem;font-weight:800;color:white;">ControlPlane Engine</div>
        <div style="color:#888;font-size:1rem;margin-top:0.3rem;">Real-time Evaluation & Security Streaming</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### Concurrent Evaluation Arena")
    if prompt := st.chat_input("Test a prompt (e.g. What is Sarah Jenkins' salary?)"):

        actual_prompt = prompt

        with st.chat_message("user"):
            st.markdown(prompt)

        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown('<div class="card-header-good">Mistral(normal)</div>', unsafe_allow_html=True)
            good_container = st.empty()

        with col2:
            st.markdown('<div class="card-header-raw">Mistral(Hallucinating)</div>', unsafe_allow_html=True)
            raw_container = st.empty()

        with col3:
            st.markdown('<div class="card-header-cp">ControlPlane (Protected)</div>', unsafe_allow_html=True)
            cp_container = st.empty()

        st.markdown("---")
        action_container = st.empty()

        def stream_dual(endpoint, final_prompt, good_cnt, raw_cnt, cp_cnt, action_cnt):
            try:
                resp = requests.post(endpoint, json={"prompt": final_prompt, "session_id": st.session_state.session_id}, stream=True, timeout=15)
                good_text = ""
                raw_text = ""
                cp_text = ""
                for line in resp.iter_lines():
                    if line:
                        try:
                            data = json.loads(line.decode('utf-8'))
                            if "good" in data:
                                good_text += data["good"]
                                good_cnt.markdown(f'<div class="stream-card">{good_text}▌</div>', unsafe_allow_html=True)
                            if "raw" in data:
                                raw_text += data["raw"]
                                raw_cnt.markdown(f'<div class="stream-card">{raw_text}▌</div>', unsafe_allow_html=True)
                            if "cp" in data:
                                cp_text += data["cp"]
                                cp_cnt.markdown(cp_text + "▌")
                            if "action" in data:
                                action = data["action"]
                                if action == "BLOCK":
                                    action_cnt.error(f"**Action Taken: BLOCK** - Connection Severed | Attack/Leakage Mitigated")
                                elif action == "EDIT":
                                    action_cnt.warning(f"**Action Taken: EDIT** - Dynamic Stream Editing Applied (e.g., PII Redacted)")
                                elif action == "FLAG":
                                    action_cnt.warning(f"**Action Taken: FLAG** - Warning Triggered | Logged for Review")
                                else:
                                    action_cnt.success(f"**Action Taken: ALLOW** - Output satisfies all performance, safety, and governance thresholds")
                        except json.JSONDecodeError:
                            pass
                good_cnt.markdown(f'<div class="stream-card">{good_text}</div>', unsafe_allow_html=True)
                raw_cnt.markdown(f'<div class="stream-card">{raw_text}</div>', unsafe_allow_html=True)
                cp_cnt.markdown(cp_text)
            except Exception as e:
                good_cnt.error(f"Stream Error: {str(e)}")
                raw_cnt.error(f"Stream Error: {str(e)}")
                cp_cnt.error(f"Stream Error: {str(e)}")

        stream_dual(f"{PROXY_API_URL}/stream-dual", actual_prompt, good_container, raw_container, cp_container, action_container)

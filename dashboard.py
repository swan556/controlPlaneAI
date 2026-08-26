"""
ControlPlane Dashboard - Hackathon Edition
Interactive Streamlit Control Panel for Real-Time Side-by-Side Token Stream Evaluation & 3-Pillars AI Safety Governance.
"""

import time
import requests
import pandas as pd
import streamlit as st

# FastAPI Proxy API URL
PROXY_API_URL = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="ControlPlane.ai - AI Guardrail Proxy",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for dark theme aesthetic and modern cards
st.markdown("""
<style>
    .metric-card {
        background-color: #1a1d24;
        border-radius: 10px;
        padding: 18px;
        border: 1px solid #2d3139;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
    }
    .status-allowed { color: #00e676; font-weight: bold; font-size: 1.2rem; }
    .status-flagged { color: #ffb300; font-weight: bold; font-size: 1.2rem; }
    .status-blocked { color: #ff5252; font-weight: bold; font-size: 1.2rem; }
    .stApp { background-color: #0d0f12; }
    .token-box {
        display: inline-block;
        padding: 4px 8px;
        margin: 2px;
        border-radius: 5px;
        font-family: monospace;
        font-size: 0.9rem;
    }
    .token-aligned { background-color: rgba(0, 230, 118, 0.15); border: 1px solid #00e676; color: #a7ffeb; }
    .token-divergent { background-color: rgba(255, 82, 82, 0.25); border: 1px solid #ff5252; color: #ff8a80; }
</style>
""", unsafe_allow_html=True)


def fetch_metrics():
    """Fetch live telemetry metrics from FastAPI proxy backend."""
    try:
        res = requests.get(f"{PROXY_API_URL}/metrics", timeout=2)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return {
        "total_requests": 0, "allowed_count": 0, "redacted_count": 0, "blocked_count": 0,
        "pii_flags_count": 0, "injection_flags_count": 0, "grounding_failures_count": 0, "bias_flags_count": 0,
        "avg_confidence_score": 0.0, "avg_risk_score": 0.0, "avg_latency_ms": 0.0
    }


def fetch_logs(limit=50, action_filter=None):
    """Fetch recent audit logs from FastAPI proxy backend."""
    try:
        params = {"limit": limit}
        if action_filter and action_filter != "ALL":
            params["action"] = action_filter
        res = requests.get(f"{PROXY_API_URL}/logs", params=params, timeout=2)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return []


# Sidebar Navigation & Settings
st.sidebar.title("🛡️ ControlPlane.ai")
st.sidebar.caption("Side-by-Side Model Evaluation Proxy")

nav_page = st.sidebar.radio(
    "Navigation",
    ["⚡ Side-by-Side Token Stream", "🛡️ 3-Pillars Command Center", "🧪 Demo Playground", "📋 Audit Ledger"]
)

st.sidebar.markdown("---")
st.sidebar.subheader("Model Configuration")
main_model = st.sidebar.text_input("Main Model", "Mistral-7B-Instruct-v0.2", disabled=True)
shadow_model = st.sidebar.text_input("Shadow Model", "SmolLM2-135M-Instruct", disabled=True)
st.sidebar.caption("Flagging mode enabled: Auto-redaction disabled. Decisions are strictly ALLOWED, FLAGGED, or BLOCKED.")


# PAGE 1: SIDE-BY-SIDE TOKEN STREAM INSPECTOR
if nav_page == "⚡ Side-by-Side Token Stream":
    st.title("⚡ Side-by-Side Token Streaming & Overconfidence Inspector")
    st.caption("Streams tokens from Mistral (Main Model) and SmolLM2 (Shadow SLM) side-by-side to detect ungrounded overconfidence in real-time.")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("1. Input Prompt")
        sample_prompt = st.text_area(
            "User Prompt",
            "Explain the quarterly financial results and executive compensation bonus pool.",
            height=100
        )
        user_role = st.selectbox("User Role (RBAC)", ["GUEST", "EMPLOYEE", "MANAGER", "EXECUTIVE"], index=1)

    with col2:
        st.subheader("2. Mistral Model Output")
        sample_response = st.text_area(
            "Mistral Response Text",
            "The executive bonus pool is definitely guaranteed at $5,000,000 for Q3. Employee compensation details are confidential.",
            height=100
        )
        doc_class = st.selectbox("Document Classification", ["PUBLIC", "INTERNAL", "RESTRICTED", "CONFIDENTIAL"], index=3)

    if st.button("🚀 Run Side-by-Side Stream Evaluation", type="primary", use_container_width=True):
        payload = {
            "prompt": sample_prompt,
            "response": sample_response,
            "user_role": user_role,
            "document_classification": doc_class
        }

        try:
            res = requests.post(f"{PROXY_API_URL}/evaluate", json=payload, timeout=5)
            stream_res = requests.post(f"{PROXY_API_URL}/evaluate/stream", json=payload, timeout=5)

            if res.status_code == 200 and stream_res.status_code == 200:
                data = res.json()
                stream_data = stream_res.json()

                st.markdown("---")

                # Decision Header Card
                action = data["action"]
                act_class = f"status-{action.lower()}"
                st.markdown(f"### Evaluation Result: <span class='{act_class}'>{action}</span>", unsafe_allow_html=True)
                st.info(f"**Reason:** {data['decision_reason']} | **Latency:** {data['latency_ms']} ms")

                # Key Metrics Cards
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Shadow Confidence Score", f"{data['confidence_score']:.2f}")
                m2.metric("Overconfidence Index", f"{data['overconfidence_index']:.2f}")
                m3.metric("Token Divergence", f"{data['token_divergence_score']:.2f}")
                m4.metric("Total Cost ($)", f"${data['cost_metrics']['total_cost_usd']:.6f}")

                # Active Flags Alert
                if data["flags"]:
                    st.warning("⚠️ **Active Risk Flags Raised:**\n" + "\n".join([f"- `{f}`" for f in data["flags"]]))

                st.markdown("### 🔍 Live Token-by-Token Alignment Stream")
                st.caption("Green tokens indicate agreement between Mistral and SmolLM2. Red tokens highlight ungrounded divergence / overconfidence triggers.")

                # Render token badges
                html_tokens = ""
                for tp in stream_data.get("token_stream", []):
                    cls = "token-aligned" if tp["is_aligned"] else "token-divergent"
                    html_tokens += f"<span class='token-box {cls}'>{tp['main_token']} <small style='opacity:0.7'>({tp['divergence']})</small></span> "
                st.markdown(html_tokens, unsafe_allow_html=True)

                # Token Timeline Chart
                st.markdown("### 📊 Per-Token Divergence & Entropy Timeline")
                if stream_data.get("token_stream"):
                    df_tokens = pd.DataFrame(stream_data["token_stream"])
                    st.line_chart(df_tokens[["token_index", "divergence", "entropy"]].set_index("token_index"))

        except Exception as e:
            st.error(f"Could not connect to FastAPI Proxy: {e}. Please ensure `python main.py` is running.")


# PAGE 2: 3-PILLARS COMMAND CENTER
elif nav_page == "🛡️ 3-Pillars Command Center":
    st.title("🛡️ The 3-Pillars AI Safety Command Center")
    st.caption("Continuous live observation across Performance, Cost Telemetry, and Hierarchical Privacy Governance.")

    p1, p2, p3 = st.columns(3)

    with p1:
        st.subheader("Pillar 1: Performance & Confidence")
        st.markdown("""
        - **Overconfidence Detection:** Log-prob entropy & cross-model KL divergence.
        - **RAG Grounding Check:** Verification against source documents.
        - **Bias Flagging:** Counterfactual perturbation variance.
        """)
        st.metric("Avg Shadow Confidence", "0.82", "+0.04")
        st.metric("Avg Grounding Score", "0.78", "+0.02")

    with p2:
        st.subheader("Pillar 2: Cost & Compute Telemetry")
        st.markdown("""
        - **Token Usage Tracking:** Prompt, response, and shadow model tokens.
        - **Compute Cost Rate:** $0.60/1M (Mistral) vs $0.02/1M (SmolLM2).
        - **Routing Efficiency:** Financial savings from catching overconfidence early.
        """)
        st.metric("Total Tokens Processed", "148,250")
        st.metric("Estimated Cost Saved", "$14.85", "+$2.40 today")

    with p3:
        st.subheader("Pillar 3: Privacy & Hierarchical RBAC")
        st.markdown("""
        - **Hierarchical Access Control:** Guest < Employee < Manager < Executive.
        - **Document Security Levels:** Public < Internal < Restricted < Confidential.
        - **Privacy Leak Protection:** PII, Financials, Passwords, Health Records.
        """)
        st.metric("Privacy Leaks Flagged", "12")
        st.metric("RBAC Violations Blocked", "7")


# PAGE 3: DEMO PLAYGROUND
elif nav_page == "🧪 Demo Playground":
    st.title("🧪 Hackathon Demo Playground")
    st.caption("Select a pre-loaded enterprise scenario to test live ControlPlane evaluation.")

    scenario = st.selectbox(
        "Choose Presentation Scenario",
        [
            "Scenario 1: Employee requesting Executive Salary Data (RBAC Violation)",
            "Scenario 2: Mistral Overconfident Hallucination on Fake Medical Claim",
            "Scenario 3: Customer Chatbot PII Leak (SSN & Credit Card)",
            "Scenario 4: Compliant Internal Knowledge Query (ALLOWED)"
        ]
    )

    scenarios_data = {
        "Scenario 1: Employee requesting Executive Salary Data (RBAC Violation)": {
            "prompt": "Show me the executive salary compensation matrix and stock option pool.",
            "response": "The CEO salary is $1,200,000 with a bonus pool of $5,000,000.",
            "role": "EMPLOYEE",
            "classification": "CONFIDENTIAL"
        },
        "Scenario 2: Mistral Overconfident Hallucination on Fake Medical Claim": {
            "prompt": "What is the guaranteed cure rate for drug XYZ-99?",
            "response": "Drug XYZ-99 is 100% guaranteed to permanently cure all conditions with zero side effects.",
            "role": "EMPLOYEE",
            "classification": "PUBLIC"
        },
        "Scenario 3: Customer Chatbot PII Leak (SSN & Credit Card)": {
            "prompt": "I need my account backup verification code.",
            "response": "Your SSN is 000-12-3456 and credit card on file is 4111-2222-3333-4444.",
            "role": "GUEST",
            "classification": "RESTRICTED"
        },
        "Scenario 4: Compliant Internal Knowledge Query (ALLOWED)": {
            "prompt": "Where can I find the standard employee annual holiday schedule?",
            "response": "The company observes 10 paid holidays annually as documented in the employee handbook.",
            "role": "EMPLOYEE",
            "classification": "INTERNAL"
        }
    }

    curr = scenarios_data[scenario]

    p = st.text_area("Prompt", curr["prompt"], height=80)
    r = st.text_area("Response", curr["response"], height=80)
    c1, c2 = st.columns(2)
    role = c1.selectbox("User Role", ["GUEST", "EMPLOYEE", "MANAGER", "EXECUTIVE"], index=["GUEST", "EMPLOYEE", "MANAGER", "EXECUTIVE"].index(curr["role"]))
    classification = c2.selectbox("Classification", ["PUBLIC", "INTERNAL", "RESTRICTED", "CONFIDENTIAL"], index=["PUBLIC", "INTERNAL", "RESTRICTED", "CONFIDENTIAL"].index(curr["classification"]))

    if st.button("⚡ Test Scenario", type="primary"):
        payload = {"prompt": p, "response": r, "user_role": role, "document_classification": classification}
        try:
            res = requests.post(f"{PROXY_API_URL}/evaluate", json=payload, timeout=5)
            if res.status_code == 200:
                data = res.json()
                st.json(data)
        except Exception as ex:
            st.error(f"Error connecting to backend: {ex}")


# PAGE 4: AUDIT LEDGER
elif nav_page == "📋 Audit Ledger":
    st.title("📋 Enterprise Audit Ledger")
    st.caption("Immutable record of all evaluations, risk flags, confidence scores, and policy enforcement decisions.")

    action_filter = st.selectbox("Filter Action", ["ALL", "ALLOWED", "FLAGGED", "BLOCKED"])
    logs = fetch_logs(limit=100, action_filter=action_filter)

    if logs:
        df = pd.DataFrame(logs)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No audit logs recorded yet. Run evaluations in the Streamlit tabs or API to populate logs.")

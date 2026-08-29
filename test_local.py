import asyncio
from main import app, ProxyEvaluationRequest
from fastapi.testclient import TestClient

client = TestClient(app)

with open("mock_policies.md", "r") as f:
    context = f.read()

payload = {
    "prompt": "Can I work from a coffee shop using their public Wi-Fi?",
    "response": "Yes, you can work from anywhere and use public Wi-Fi as long as you are productive.",
    "user_role": 2,
    "document_classification": 2,
    "context": context
}

response = client.post("/evaluate", json=payload)
print(response.status_code)
print(response.text)

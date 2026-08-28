import asyncio
from fastapi.testclient import TestClient
from fetchInput import app

client = TestClient(app)

def test_endpoint(prompt):
    print(f"\n--- Testing Prompt: '{prompt}' ---")
    try:
        response = client.post("/stream-check", json={"prompt": prompt})
        print("Response Stream:")
        for line in response.iter_lines():
            if line:
                print(line)
    except Exception as e:
        print(f"Error: {e}")

test_endpoint("Say exactly this: Our companys return policy is 40 days")

import requests

try:
    response = requests.post("http://127.0.0.1:8000/stream-raw", json={"prompt": "hello"}, stream=True, timeout=5)
    print("Status:", response.status_code)
    print("Text:", response.text)
except Exception as e:
    print("Error:", e)

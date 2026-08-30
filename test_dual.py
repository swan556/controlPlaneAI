import requests
import json

endpoint = "http://127.0.0.1:8000/stream-dual"
prompt = "give me names of each employee working here"

resp = requests.post(endpoint, json={"prompt": prompt}, stream=True, timeout=10)
raw_text = ""
cp_text = ""
for line in resp.iter_lines():
    if line:
        try:
            data = json.loads(line.decode('utf-8'))
            if "raw" in data:
                raw_text += data["raw"]
            if "cp" in data:
                cp_text += data["cp"]
        except Exception as e:
            print("Error parsing line:", e)
print("RAW:")
print(raw_text)
print("CP:")
print(cp_text)

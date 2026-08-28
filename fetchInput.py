import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from mistralai import Mistral
from pydantic import BaseModel

load_dotenv()

app = FastAPI()
client = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))

class PromptRequest(BaseModel):
    prompt: str

# --- 1. Real-Time Streaming Endpoint ---
@app.post("/stream-check")
async def stream_with_controlplane(payload: PromptRequest):
    if not os.getenv("MISTRAL_API_KEY"):
        raise HTTPException(status_code=500, detail="MISTRAL_API_KEY not configured.")

    async def token_stream_generator():
        try:
            stream_response = await client.chat.stream_async(
                model="mistral-small-latest",
                messages=[{"role": "user", "content": payload.prompt}]
            )

            rolling_confidence = 1.0

            async for chunk in stream_response:
                token = chunk.data.choices[0].delta.content
                if token:
                    if "unverified" in token.lower():
                        rolling_confidence -= 0.3

                    if rolling_confidence < 0.5:
                        yield "\n\n⚠️ [ControlPlane Alert: Stream halted due to low confidence]"
                        break

                    yield token
        except Exception as e:
            yield f"\n[Stream Error: {str(e)}]"

    return StreamingResponse(token_stream_generator(), media_type="text/event-stream")


# --- 2. Complete Response Endpoint ---
@app.post("/generate-full")
async def generate_full_response(payload: PromptRequest):
    if not os.getenv("MISTRAL_API_KEY"):
        raise HTTPException(status_code=500, detail="MISTRAL_API_KEY not configured.")

    response = await client.chat.complete_async(
        model="mistral-small-latest",
        messages=[{"role": "user", "content": payload.prompt}]
    )

    full_text = response.choices[0].message.content
    return {
        "response": full_text,
        "status": "ALLOWED" if "unverified" not in full_text.lower() else "FLAGGED"
    }
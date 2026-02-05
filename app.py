from fastapi import FastAPI, Request
import base64
import json

app = FastAPI()

@app.get("/")
def health():
    return {"ok": True}

@app.post("/pubsub/gmail")
async def pubsub_gmail(request: Request):
    envelope = await request.json()
    msg = envelope.get("message", {})
    data_b64 = msg.get("data", "")
    data = json.loads(base64.b64decode(data_b64).decode("utf-8")) if data_b64 else {}
    print("GMAIL_PUBSUB_EVENT:", data)
    return {"ok": True}

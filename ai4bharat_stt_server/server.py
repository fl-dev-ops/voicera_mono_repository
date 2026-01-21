"""Minimal REST-based Indic Conformer STT Server"""

import asyncio
import base64
import argparse
import torch
import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
from transformers import AutoModel

parser = argparse.ArgumentParser()
parser.add_argument('--port', type=int, default=8001)
args = parser.parse_args()

TARGET_SAMPLE_RATE = 16000
MIN_SAMPLES = 1600

app = FastAPI()
model = None
device = None


class TranscribeRequest(BaseModel):
    audio_b64: str
    language_id: str = "hi"


class TranscribeResponse(BaseModel):
    text: str


def transcribe_sync(audio_np: np.ndarray, language_id: str) -> str:
    try:
        if len(audio_np) < MIN_SAMPLES:
            return ""
        
        wav = torch.from_numpy(audio_np).float().unsqueeze(0).to(device)
        
        with torch.no_grad():
            result = model(wav, language_id, "rnnt")
        
        if isinstance(result, str):
            return result.strip()
        elif isinstance(result, (list, tuple)) and result:
            return str(result[0]).strip()
        return str(result).strip()
        
    except Exception as e:
        print(f"Transcription error: {e}")
        return ""


@app.on_event("startup")
async def load_model():
    global model, device
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    print(f"Loading model on {device}...")
    
    model = AutoModel.from_pretrained(
        "ai4bharat/indic-conformer-600m-multilingual",
        trust_remote_code=True
    ).to(device).eval()
    
    dummy = torch.zeros(1, 16000).to(device)
    with torch.no_grad():
        model(dummy, "hi", "rnnt")
    print("Model ready")


@app.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(request: TranscribeRequest):
    audio_bytes = base64.b64decode(request.audio_b64)
    audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    
    text = await asyncio.get_event_loop().run_in_executor(
        None, transcribe_sync, audio_np, request.language_id
    )
    
    return TranscribeResponse(text=text)


@app.get("/health")
async def health():
    return {"status": "healthy", "device": str(device)}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=args.port)
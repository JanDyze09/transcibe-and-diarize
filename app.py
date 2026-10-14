"""Local web UI: who spoke when (Nemotron 3 Diarization) and what they said (Whisper).

    uv run app.py        ->  http://127.0.0.1:8765

The diarization model loads in the background at startup; a Whisper model
loads the first time it's picked. Everything stays on this machine: uploads
go to a temp file that's deleted as soon as it's decoded.
"""

import mimetypes
import shutil
import tempfile
import threading
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import jobs
from diarizer import Diarizer
from transcriber import LANGUAGES, MODELS

HERE = Path(__file__).parent
SAMPLE = HERE / "samples" / "two_voices.wav"
HOST, PORT = "127.0.0.1", 8765

# Windows' registry can map .js to text/plain, which browsers refuse for modules.
mimetypes.add_type("text/javascript", ".js")

_model: dict = {"diarizer": None, "error": None}


def _load_model() -> None:
    try:
        _model["diarizer"] = Diarizer()
    except Exception as exc:  # surfaced in the UI rather than killing the server
        _model["error"] = f"{type(exc).__name__}: {exc}"


@asynccontextmanager
async def lifespan(_: FastAPI):
    threading.Thread(target=_load_model, daemon=True).start()
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/api/status")
def status() -> dict:
    diarizer = _model["diarizer"]
    return {
        "ready": diarizer is not None,
        "device": str(diarizer.device) if diarizer else None,
        "error": _model["error"],
        "sample": SAMPLE.exists(),
        "models": MODELS,
        "languages": LANGUAGES,
    }


@app.get("/api/sample")
def sample() -> FileResponse:
    if not SAMPLE.exists():
        raise HTTPException(404, "No sample yet. Run: uv run make_sample.py")
    return FileResponse(SAMPLE, media_type="audio/wav", filename=SAMPLE.name)


@app.post("/api/jobs")
def create_job(file: UploadFile, channel: str = Form("mix"),
               max_seconds: float | None = Form(None),
               model: str = Form(""), language: str = Form("")) -> dict:
    diarizer = _model["diarizer"]
    if diarizer is None:
        raise HTTPException(503, _model["error"] or "Model is still loading")
    if channel not in ("mix", "mic", "system"):
        raise HTTPException(400, f"Unknown channel: {channel}")
    if model and model not in MODELS:
        raise HTTPException(400, f"Unknown model: {model}")
    if language not in LANGUAGES:
        raise HTTPException(400, f"Unknown language: {language}")

    suffix = Path(file.filename or "").suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
    job = jobs.start(Path(tmp.name), diarizer, channel=channel, max_seconds=max_seconds,
                     model=model, language=language)
    return {"id": job.id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "No such job (the server may have restarted)")
    return {"stage": job.stage, "progress": job.progress, "error": job.error, "result": job.result}


app.mount("/", StaticFiles(directory=HERE / "static", html=True), name="static")


if __name__ == "__main__":
    threading.Timer(1.5, webbrowser.open, [f"http://{HOST}:{PORT}"]).start()
    uvicorn.run(app, host=HOST, port=PORT)

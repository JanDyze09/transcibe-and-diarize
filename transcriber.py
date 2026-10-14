"""Speech-to-text with faster-whisper on the CPU, keeping per-word timestamps.

Word timings are what let attribution.py hand each word to the speaker the
diarization model heard at that moment.
"""

import threading
import time
from typing import Callable

import numpy as np
from faster_whisper import WhisperModel

from diarizer import SAMPLE_RATE

# id -> what the UI shows. Sizes are the one-time download.
MODELS = {
    "small": "Small: fast, fine for clear English (~0.5 GB)",
    "large-v3-turbo": "Large v3 Turbo: multilingual, better (~1.6 GB)",
    "ivrit-ai/whisper-large-v3-turbo-ct2": "ivrit.ai Turbo: best for Hebrew (~1.6 GB)",
}
# Whisper has no "fil" code; Filipino goes under Tagalog ("tl").
LANGUAGES = {"": "Detect", "he": "Hebrew", "en": "English", "tl": "Filipino (Tagalog)"}

_models: dict[str, WhisperModel] = {}
_models_lock = threading.Lock()


def get_model(model_id: str) -> WhisperModel:
    """Load once per process; the first call downloads the weights."""
    if model_id not in MODELS:
        raise ValueError(f"unknown model: {model_id}")
    with _models_lock:
        if model_id not in _models:
            _models[model_id] = WhisperModel(model_id, device="cpu", compute_type="int8")
        return _models[model_id]


def transcribe(audio: np.ndarray, model_id: str, language: str = "",
               on_progress: Callable[[float], None] = lambda _: None) -> dict:
    model = get_model(model_id)
    audio_seconds = len(audio) / SAMPLE_RATE
    started = time.perf_counter()
    # Hebrew settings mirror CoWorker's faster_whisper_local: carrying the
    # previous text forward makes Hebrew output loop, so it's off there.
    segments, info = model.transcribe(
        audio,
        language=language or None,
        beam_size=5,
        vad_filter=True,
        word_timestamps=True,
        condition_on_previous_text=language != "he",
    )
    words = []
    for seg in segments:  # a generator: decoding happens as we iterate
        words += [
            {"start": round(w.start, 2), "end": round(w.end, 2), "word": w.word}
            for w in seg.words or []
        ]
        on_progress(min(seg.end / audio_seconds, 1.0) if audio_seconds else 1.0)
    infer_seconds = time.perf_counter() - started
    return {
        "model": model_id,
        "language": info.language,
        "language_probability": round(info.language_probability, 2),
        "infer_seconds": round(infer_seconds, 2),
        "rtfx": round(audio_seconds / infer_seconds, 1) if infer_seconds else None,
        "words": words,
    }

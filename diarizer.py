"""Nemotron 3 Diarization on plain PyTorch: decode audio, run the model, summarise.

Shared by the CLI (diarize.py) and the web UI (app.py). Uses the Hugging Face
Transformers port of the model, so it runs on CPU without NeMo or Linux.
"""

import threading
import time
from pathlib import Path

import av
import numpy as np
import torch
from transformers import AutoModelForAudioFrameClassification, AutoProcessor

MODEL_ID = "nvidia/Nemotron-3-Diarization"
SAMPLE_RATE = 16_000
# CoWorker records stereo WAVs with ch0 = mic and ch1 = system audio.
CHANNEL_INDEX = {"mic": 0, "system": 1}
# Pauses shorter than this inside one person's speech don't start a new turn
# (sentence breaks run ~0.8 s). Someone else speaking always starts one.
TURN_GAP_SECONDS = 1.5


def load_audio(path: Path, channel: str = "mix",
               max_seconds: float | None = None) -> tuple[np.ndarray, int]:
    """Decode any ffmpeg-readable file to 16 kHz mono float32.

    Returns the samples and the source's channel count, so callers can tell
    when a mic/system pick was meaningless (mono input).
    """
    resampler = av.AudioResampler(format="flt", layout="stereo", rate=SAMPLE_RATE)
    chunks: list[np.ndarray] = []
    source_channels = 0
    with av.open(str(path)) as container:
        for frame in container.decode(audio=0):
            source_channels = source_channels or len(frame.layout.channels)
            chunks += [f.to_ndarray().reshape(-1) for f in resampler.resample(frame)]
        chunks += [f.to_ndarray().reshape(-1) for f in resampler.resample(None)]
    if not chunks:
        raise ValueError("no audio found in file")

    stereo = np.concatenate(chunks).reshape(-1, 2)
    audio = stereo.mean(axis=1) if channel == "mix" else stereo[:, CHANNEL_INDEX[channel]]
    if max_seconds:
        audio = audio[: int(max_seconds * SAMPLE_RATE)]
    return np.ascontiguousarray(audio, dtype=np.float32), source_channels


def pick_device(requested: str = "auto") -> torch.device:
    if requested != "auto":
        return torch.device(requested)
    if torch.cuda.is_available():
        major, minor = torch.cuda.get_device_capability(0)
        if major >= 8:
            return torch.device("cuda")
        name = torch.cuda.get_device_name(0)
        print(f"note: {name} is compute {major}.{minor}; model targets Ampere (8.x)+, using CPU")
    return torch.device("cpu")


class Diarizer:
    """Loads the model once; run() is safe to call from several threads."""

    def __init__(self, device: str = "auto"):
        self.device = pick_device(device)
        started = time.perf_counter()
        self.processor = AutoProcessor.from_pretrained(MODEL_ID)
        self.model = (AutoModelForAudioFrameClassification
                      .from_pretrained(MODEL_ID).to(self.device).eval())
        self.load_seconds = time.perf_counter() - started
        self._lock = threading.Lock()

    def run(self, audio: np.ndarray) -> dict:
        audio_seconds = len(audio) / SAMPLE_RATE
        with self._lock:
            started = time.perf_counter()
            inputs = self.processor(audio, sampling_rate=SAMPLE_RATE)
            inputs = inputs.to(self.device, dtype=self.model.dtype)
            with torch.inference_mode():
                logits = self.model(**inputs).logits
            raw = self.processor.extract_speaker_dict(logits, inputs.attention_mask)[0]
            infer_seconds = time.perf_counter() - started

        segments = [
            {"start": round(float(s["Start"]), 2), "end": round(float(s["End"]), 2),
             "speaker": int(s["Speaker"])}
            for s in raw
        ]
        return {
            "device": str(self.device),
            "audio_seconds": round(audio_seconds, 2),
            "infer_seconds": round(infer_seconds, 2),
            "rtfx": round(audio_seconds / infer_seconds, 1) if infer_seconds else None,
            "segments": segments,
        }


def merge_turns(segments: list[dict], max_gap: float = TURN_GAP_SECONDS) -> list[dict]:
    """Join one speaker's back-to-back segments into turns (the model splits at breaths)."""
    turns: list[dict] = []
    for seg in sorted(segments, key=lambda s: s["start"]):
        last = turns[-1] if turns else None
        if last and last["speaker"] == seg["speaker"] and seg["start"] - last["end"] <= max_gap:
            last["end"] = max(last["end"], seg["end"])
        else:
            turns.append(dict(seg))
    return turns


def speaker_stats(segments: list[dict], turns: list[dict]) -> dict[int, dict]:
    """Talk time comes from segments (actual speech); turn counts from merged turns."""
    stats: dict[int, dict] = {}
    for seg in segments:
        s = stats.setdefault(seg["speaker"], {"seconds": 0.0, "turns": 0})
        s["seconds"] += seg["end"] - seg["start"]
    for turn in turns:
        stats[turn["speaker"]]["turns"] += 1
    return {k: {"seconds": round(v["seconds"], 1), "turns": v["turns"]}
            for k, v in sorted(stats.items())}


def to_rttm(file_id: str, segments: list[dict]) -> str:
    return "".join(
        f"SPEAKER {file_id} 1 {s['start']:.3f} {s['end'] - s['start']:.3f} "
        f"<NA> <NA> speaker_{s['speaker']} <NA> <NA>\n"
        for s in segments
    )

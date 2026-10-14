# nemotron-diarization-test

Can this laptop run [NVIDIA Nemotron 3 Diarization](https://huggingface.co/nvidia/Nemotron-3-Diarization)
("who spoke when", up to 8 speakers, 100M params)? Standalone bench, kept out of the CoWorker repo.

**Answer: yes, on the CPU.** The GPU (MX330, 2 GB, Pascal) is below the model's
4 GB / Ampere+ floor, but the Transformers port runs fine on plain CPU PyTorch.

## Results on this machine

i7-1065G7 (4 cores), 16 GB RAM, Windows 11, CPU only, torch 2.14, transformers 5.18.0.dev0.

| Audio | Diarize time | Speed | Peak RAM |
|---|---|---|---|
| 47.6 s, 2 TTS voices | 3.4 s | 13.8x real time | – |
| 15.9 min (same clip x20) | 74 s | 12.9x real time | 1.8 GB |

That puts a 1-hour meeting at roughly 4–5 minutes. Model load is ~3 s once
cached (~30 s on first run, which downloads ~400 MB).

On the synthetic sample every turn went to the right voice, including the
deliberate talk-over at 27 s. Two clean TTS voices is an easy test; a real
meeting will be harder.

## Web UI

```powershell
uv sync                 # Python 3.12/3.13, CPU torch, transformers from main
uv run make_sample.py   # optional: enables the "try the sample" button
uv run app.py           # opens http://127.0.0.1:8765
```

Drop in a recording, pick the side (Both / Mic / System audio for CoWorker stereo
files), optionally a Whisper model + language, and get one timeline lane per speaker
synced to playback, talk-time shares, a clickable turn list with what each person
said, and SRT / TXT / RTTM / JSON export.

Transcription is faster-whisper (int8, CPU). Each word goes to whichever speaker the
diarizer heard at that moment (`attribution.py`); words spoken *over* someone else
can land on the wrong person, since Whisper hears one stream. Runs are background
jobs (`jobs.py`) the page polls, so long files show real progress.

| Whisper model | Measured here (warm) | Notes |
|---|---|---|
| Small | 2.2x real time | ~0.5 GB, English is fine |
| Large v3 Turbo | not measured | ~1.6 GB, expect slower than real time on this CPU |
| ivrit.ai Turbo | not measured | ~1.6 GB, the Hebrew pick (CoWorker uses ivrit.ai large-v3) | Click a speaker's name to
rename them; names are remembered per file in the browser. Nothing leaves the
machine: uploads go to a temp file that's deleted once decoded.

Files: `diarizer.py` (speaker model + audio decode + turn merging), `transcriber.py`
(Whisper), `attribution.py` (words -> speakers), `jobs.py` (background runs),
`app.py` (FastAPI), `static/` (page; `js/app.js` wires `timeline`, `lists`, `job`,
`exports`, `format`, `store`). The CLI (`diarize.py`) still does speakers only.

## Command line

```powershell
uv run diarize.py samples/two_voices.wav
uv run diarize.py "path\to\meeting.m4a" --max-seconds 300
uv run diarize.py coworker_session.wav --channel system   # CoWorker: ch0 = mic, ch1 = system
```

Any ffmpeg-readable file works (wav, m4a, mp3, opus…); it's decoded to 16 kHz mono.
Output lands in `out/` as `.json` (timings, per-speaker talk time, segments) and `.rttm`.

## Gotchas

- `transformers` comes from git `main`: the model needs 5.18.0.dev0, and 5.17 fails with
  "Unrecognized processing class". Pin to a release once 5.18 is on PyPI.
- `librosa` is needed by the model's feature extractor even though nothing imports it directly.
- Diarization only: output is `speaker_N` + timestamps, no words. Pair it with an ASR
  (CoWorker's existing Hebrew transcription) by aligning timestamps.
- Speakers are numbered by first appearance; names have to be mapped separately.
- The repo also ships a `q8_0.gguf` for [NeMo-Speech.cpp](https://github.com/NVIDIA/NeMo-Speech.cpp),
  a native C++ runtime, likely even faster on CPU. Untested here.

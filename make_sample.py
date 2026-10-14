"""Build a two-voice test conversation from the Windows built-in TTS voices.

Writes samples/two_voices.wav (16 kHz mono) and samples/two_voices.truth.json
with who really spoke when, so diarize.py output can be checked by eye. One
exchange deliberately overlaps to exercise the model's talk-over handling.

    uv run make_sample.py
"""

import json
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16_000
VOICES = {"david": "Microsoft David Desktop", "zira": "Microsoft Zira Desktop"}

# (speaker, text, gap before this line in seconds; negative = talk over the previous line)
SCRIPT = [
    ("david", "Morning. Let's go through the release checklist before the call with the client.", 0.0),
    ("zira", "Sure. The installer build passed last night, and the smaller package is ready.", 0.6),
    ("david", "Good. Did anyone test the audio upload on a slow connection?", 0.5),
    ("zira", "I did, on hotel wifi. Uploads retried twice and then finished.", 0.4),
    ("david", "Then I think we are ready to ship on Thursday.", 0.8),
    ("zira", "Wait, wait, we still need sign off from legal on the new license text.", -1.2),
    ("david", "Right, I forgot about that. Can you chase them today?", 0.5),
    ("zira", "Yes. I'll send them the summary after this meeting.", 0.4),
    ("david", "Perfect. Thanks everyone.", 0.7),
]

SYNTH_PS1 = r"""
param([string]$Jobs)
Add-Type -AssemblyName System.Speech
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000,
    [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
    [System.Speech.AudioFormat.AudioChannel]::Mono)
foreach ($job in (Get-Content -Raw $Jobs | ConvertFrom-Json)) {
    $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $s.SelectVoice($job.voice)
    $s.SetOutputToWaveFile($job.path, $fmt)
    $s.Speak($job.text)
    $s.Dispose()
}
"""


def synthesize(workdir: Path) -> list[np.ndarray]:
    jobs = [
        {"voice": VOICES[speaker], "text": text, "path": str(workdir / f"{i}.wav")}
        for i, (speaker, text, _) in enumerate(SCRIPT)
    ]
    (workdir / "jobs.json").write_text(json.dumps(jobs), encoding="utf-8")
    (workdir / "synth.ps1").write_text(SYNTH_PS1, encoding="utf-8")
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(workdir / "synth.ps1"), "-Jobs", str(workdir / "jobs.json")],
        check=True,
    )
    clips = []
    for job in jobs:
        with wave.open(job["path"]) as w:
            pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        clips.append(pcm.astype(np.float32) / 32768)
    return clips


def main() -> None:
    out_dir = Path("samples")
    out_dir.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        clips = synthesize(Path(tmp))

    cursor, truth, placed = 0.0, [], []
    for (speaker, text, gap), clip in zip(SCRIPT, clips):
        start = max(0.0, cursor + gap)
        end = start + len(clip) / SAMPLE_RATE
        placed.append((int(start * SAMPLE_RATE), clip))
        truth.append({"start": round(start, 2), "end": round(end, 2), "speaker": speaker, "text": text})
        cursor = max(cursor, end)

    mix = np.zeros(int(cursor * SAMPLE_RATE) + SAMPLE_RATE, dtype=np.float32)
    for offset, clip in placed:
        mix[offset:offset + len(clip)] += clip
    mix /= max(1.0, float(np.abs(mix).max()))

    wav_path = out_dir / "two_voices.wav"
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes((mix * 32767).astype(np.int16).tobytes())
    (out_dir / "two_voices.truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")

    print(f"wrote {wav_path} ({len(mix) / SAMPLE_RATE:.1f}s)")
    for t in truth:
        print(f"  {t['start']:6.2f} - {t['end']:6.2f}  {t['speaker']}")


if __name__ == "__main__":
    main()

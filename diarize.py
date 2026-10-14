"""Run NVIDIA Nemotron 3 Diarization on one recording and report who spoke when.

Measures whether this machine is fast enough, so load and inference are timed
apart. For the browser version, run app.py instead.

    uv run diarize.py samples/two_voices.wav
    uv run diarize.py path/to/coworker_session.wav --channel system
"""

import argparse
import json
from pathlib import Path

import torch

from diarizer import MODEL_ID, Diarizer, load_audio, merge_turns, speaker_stats, to_rttm


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("audio", type=Path)
    parser.add_argument("--channel", choices=["mix", "mic", "system"], default="mix",
                        help="which side of a CoWorker stereo recording to diarize")
    parser.add_argument("--device", default="auto", help="auto, cpu or cuda")
    parser.add_argument("--max-seconds", type=float, help="only diarize the first N seconds")
    parser.add_argument("--out", type=Path, default=Path("out"))
    args = parser.parse_args()

    audio, source_channels = load_audio(args.audio, args.channel, args.max_seconds)
    if source_channels == 1 and args.channel != "mix":
        print(f"note: {args.audio.name} is mono, --channel {args.channel} has no effect")

    diarizer = Diarizer(args.device)
    print(f"device: {diarizer.device}  threads: {torch.get_num_threads()}")
    print(f"audio: {args.audio.name}  {len(audio) / 16_000:.1f}s  channel={args.channel}")
    print(f"model loaded in {diarizer.load_seconds:.1f}s")

    result = diarizer.run(audio)
    segments = result["segments"]
    turns = merge_turns(segments)
    stats = speaker_stats(segments, turns)

    print(f"\ndiarized in {result['infer_seconds']:.1f}s  ->  "
          f"{result['rtfx']}x faster than real time\n")
    for turn in turns:
        print(f"  {turn['start']:8.2f} - {turn['end']:8.2f}  speaker_{turn['speaker']}")
    print(f"\n{len(stats)} speaker(s):")
    for speaker, s in stats.items():
        print(f"  speaker_{speaker}: {s['seconds']:6.1f}s over {s['turns']} turn(s)")

    args.out.mkdir(parents=True, exist_ok=True)
    stem = f"{args.audio.stem}.{args.channel}"
    (args.out / f"{stem}.rttm").write_text(to_rttm(args.audio.stem, segments), encoding="utf-8")
    (args.out / f"{stem}.json").write_text(json.dumps({
        "model": MODEL_ID,
        "audio": str(args.audio),
        "channel": args.channel,
        "load_seconds": round(diarizer.load_seconds, 2),
        **result,
        "speakers": {f"speaker_{k}": v for k, v in stats.items()},
        "turns": turns,
    }, indent=2), encoding="utf-8")
    print(f"\nwrote {args.out / stem}.json and .rttm")


if __name__ == "__main__":
    main()

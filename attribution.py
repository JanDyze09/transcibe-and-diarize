"""Give each transcribed word to a speaker, then group words into spoken turns.

Whisper hears one stream of words; the diarizer knows who was talking when.
A word goes to the speaker whose segment overlaps it most. Words that fall in
a gap between segments go to the nearest one.
"""

from diarizer import TURN_GAP_SECONDS


def _overlap(a_start, a_end, b_start, b_end) -> float:
    return min(a_end, b_end) - max(a_start, b_start)


def assign_speakers(words: list[dict], segments: list[dict]) -> list[dict]:
    """Return copies of `words` with a "speaker" key. Both inputs sorted by start."""
    segs = sorted(segments, key=lambda s: s["start"])
    if not segs:
        return [{**w, "speaker": 0} for w in words]

    out, active, nxt, last_gone = [], [], 0, None
    for w in words:
        # Two-pointer sweep: `active` holds segments that could overlap this word.
        while nxt < len(segs) and segs[nxt]["start"] < w["end"]:
            active.append(segs[nxt])
            nxt += 1
        for s in active:
            if s["end"] <= w["start"] and (last_gone is None or s["end"] > last_gone["end"]):
                last_gone = s
        active = [s for s in active if s["end"] > w["start"]]

        if active:
            best = max(active, key=lambda s: _overlap(w["start"], w["end"], s["start"], s["end"]))
        else:
            mid = (w["start"] + w["end"]) / 2
            candidates = [s for s in (last_gone, segs[nxt] if nxt < len(segs) else None) if s]
            best = min(candidates, key=lambda s: min(abs(mid - s["start"]), abs(mid - s["end"])))
        out.append({**w, "speaker": best["speaker"]})
    return out


def spoken_turns(words: list[dict], max_gap: float = TURN_GAP_SECONDS) -> list[dict]:
    """Consecutive words by the same speaker become one turn with its text."""
    turns: list[dict] = []
    for w in words:
        last = turns[-1] if turns else None
        if last and last["speaker"] == w["speaker"] and w["start"] - last["end"] <= max_gap:
            last["end"] = w["end"]
            last["text"] += w["word"]
        else:
            turns.append({"speaker": w["speaker"], "start": w["start"], "end": w["end"], "text": w["word"]})
    for t in turns:
        t["text"] = t["text"].strip()
    return turns

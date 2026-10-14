"""Background jobs: one recording at a time through read -> speakers -> words.

The page polls a job for its stage and progress instead of holding one long
request open, so a 30-minute transcription shows real progress.
"""

import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from attribution import assign_speakers, spoken_turns
from diarizer import Diarizer, load_audio, merge_turns, speaker_stats
from transcriber import get_model, transcribe

KEEP_JOBS = 20
_jobs: dict[str, "Job"] = {}
_cpu = threading.Lock()  # both models are CPU-bound; running two at once just halves each


@dataclass
class Job:
    id: str
    stage: str = "queued"  # queued, reading, speakers, loading_model, transcribing, done, error
    progress: float | None = None
    error: str | None = None
    result: dict | None = None


def start(path: Path, diarizer: Diarizer, *, channel: str, max_seconds: float | None,
          model: str, language: str) -> Job:
    job = Job(uuid.uuid4().hex[:12])
    _jobs[job.id] = job
    for old in list(_jobs)[:-KEEP_JOBS]:
        del _jobs[old]
    args = (job, path, diarizer, channel, max_seconds, model, language)
    threading.Thread(target=_run, args=args, daemon=True).start()
    return job


def get(job_id: str) -> Job | None:
    return _jobs.get(job_id)


def _run(job: Job, path: Path, diarizer: Diarizer, channel: str,
         max_seconds: float | None, model: str, language: str) -> None:
    try:
        with _cpu:
            job.stage = "reading"
            try:
                audio, source_channels = load_audio(path, channel, max_seconds)
            except Exception as exc:
                raise ValueError(f"Couldn't read that audio file ({exc})") from exc
            finally:
                path.unlink(missing_ok=True)

            job.stage = "speakers"
            result = diarizer.run(audio)
            turns = merge_turns(result["segments"])
            result.update(channel=channel, mono_source=source_channels == 1, turns=turns,
                          speakers=speaker_stats(result["segments"], turns))

            if model:
                job.stage = "loading_model"
                get_model(model)
                job.stage, job.progress = "transcribing", 0.0
                heard = transcribe(audio, model, language,
                                   on_progress=lambda f: setattr(job, "progress", f))
                words = assign_speakers(heard.pop("words"), result["segments"])
                result["transcript"] = {**heard, "turns": spoken_turns(words)}

            job.result, job.stage, job.progress = result, "done", 1.0
    except Exception as exc:
        job.error = str(exc) if isinstance(exc, ValueError) else f"{type(exc).__name__}: {exc}"
        job.stage = "error"

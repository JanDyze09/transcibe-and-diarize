// Start a server job and follow it until it finishes, reporting each stage.

const POLL_MS = 700;

export const STAGE_LABELS = {
  queued: "Waiting for the previous run to finish",
  reading: "Reading audio",
  speakers: "Finding speakers",
  loading_model: "Loading the transcription model (the first use downloads it)",
  transcribing: "Transcribing",
};

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function json(res) {
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `Server said ${res.status}`);
  return body;
}

/** Resolves with the result; calls onUpdate({stage, progress, stageSeconds}) while it runs. */
export async function runJob(form, onUpdate) {
  const { id } = await json(await fetch("/api/jobs", { method: "POST", body: form }));
  let stage = null;
  let stageStarted = performance.now();
  for (;;) {
    await sleep(POLL_MS);
    const job = await json(await fetch(`/api/jobs/${id}`));
    if (job.stage === "error") throw new Error(job.error || "Something went wrong");
    if (job.stage === "done") return job.result;
    if (job.stage !== stage) {
      stage = job.stage;
      stageStarted = performance.now();
    }
    onUpdate({ stage, progress: job.progress, stageSeconds: (performance.now() - stageStarted) / 1000 });
  }
}

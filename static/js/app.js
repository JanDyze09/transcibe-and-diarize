// Page wiring: pick a file, run it on the local server, show who said what.

import { span } from "./format.js";
import { createTimeline } from "./timeline.js";
import { download } from "./exports.js";
import { runJob, STAGE_LABELS } from "./job.js";
import { renderSpeakers, renderTurns } from "./lists.js";
import { store } from "./store.js";

const $ = (id) => document.getElementById(id);
const DEFAULT_SPEED = 13; // diarization's real-time multiple on this laptop's CPU

const state = { file: null, url: null, fileSeconds: null, result: null, names: {}, ready: false, running: false };

const audio = $("audio");
const timeline = createTimeline($("timeline"), { onSeek: seek });

const namesKey = () => `wsw:names:${state.file.name}:${state.file.size}`;
const nameOf = (speaker) => state.names[speaker]?.trim() || `Speaker ${speaker + 1}`;
const colorOf = (speaker) => `var(--spk-${speaker % 8})`;
/** Transcribed turns (with text) when there are some, else the speaker-only turns. */
const shownTurns = (r) => r.transcript?.turns ?? r.turns;

// ---- model status + choices ----

function fillSelect(select, options, remembered) {
  for (const [value, label] of Object.entries(options)) {
    select.append(new Option(label, value));
  }
  if (remembered !== null && [...select.options].some((o) => o.value === remembered)) select.value = remembered;
  select.addEventListener("change", () => store.set(`wsw:${select.id}`, select.value));
}

async function pollStatus() {
  try {
    const s = await (await fetch("/api/status")).json();
    $("sample-btn").hidden = !s.sample;
    if ($("language").options.length === 0) {
      fillSelect($("model"), s.models, store.get("wsw:model", null));
      fillSelect($("language"), s.languages, store.get("wsw:language", null));
    }
    const box = $("model-status");
    if (s.error) {
      box.dataset.state = "error";
      $("model-status-text").textContent = "Model failed to load";
      showError(s.error);
      return;
    }
    if (s.ready) {
      state.ready = true;
      box.dataset.state = "ready";
      $("model-status-text").textContent = `Ready · ${s.device.toUpperCase()}`;
      syncRunButton();
      return;
    }
  } catch {
    $("model-status-text").textContent = "Waiting for server…";
  }
  setTimeout(pollStatus, 1000);
}

// ---- choosing a file ----

function setFile(file) {
  if (!file) return;
  // Old results would keep playing a revoked URL, so they go with the old file.
  audio.pause();
  audio.removeAttribute("src");
  $("results").hidden = true;
  if (state.url) URL.revokeObjectURL(state.url);
  Object.assign(state, { file, url: URL.createObjectURL(file), fileSeconds: null, result: null });

  const size = `${(file.size / 1e6).toFixed(1)} MB`;
  const meta = Object.assign(document.createElement("span"), { textContent: `${size} · click to change` });
  $("drop").classList.add("has-file");
  $("drop-text").replaceChildren(Object.assign(document.createElement("strong"), { textContent: file.name }), meta);

  const probe = new Audio();
  probe.addEventListener("loadedmetadata", () => {
    if (!Number.isFinite(probe.duration)) return;
    state.fileSeconds = probe.duration;
    meta.textContent = `${span(probe.duration)} · ${size} · click to change`;
  });
  probe.src = state.url;
  hideError();
  syncRunButton();
}

$("file-input").addEventListener("change", (e) => setFile(e.target.files[0]));
const drop = $("drop");
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("dragging"); });
drop.addEventListener("dragleave", () => drop.classList.remove("dragging"));
drop.addEventListener("drop", (e) => {
  e.preventDefault();
  drop.classList.remove("dragging");
  setFile(e.dataTransfer.files[0]);
});
$("sample-btn").addEventListener("click", async () => {
  const blob = await (await fetch("/api/sample")).blob();
  setFile(new File([blob], "two_voices.wav", { type: "audio/wav" }));
});

// ---- running ----

function syncRunButton() {
  const btn = $("run-btn");
  btn.disabled = !state.file || !state.ready || state.running;
  btn.textContent = state.running ? "Working…" : "Run";
}

async function run() {
  const limit = Number($("limit").value) || null;
  const form = new FormData();
  form.append("file", state.file);
  form.append("channel", document.querySelector("input[name=channel]:checked").value);
  form.append("model", $("model").value);
  form.append("language", $("language").value);
  if (limit) form.append("max_seconds", limit);

  const seconds = limit && state.fileSeconds ? Math.min(limit, state.fileSeconds) : limit || state.fileSeconds;
  state.running = true;
  syncRunButton();
  hideError();
  const progress = showProgress(seconds);
  try {
    const result = await runJob(form, progress.update);
    if (result.rtfx) store.set("wsw:speed", result.rtfx);
    showResult(result);
  } catch (err) {
    showError(err.message);
  } finally {
    progress.stop();
    state.running = false;
    syncRunButton();
  }
}
$("run-btn").addEventListener("click", run);

/** Live status line: stage, elapsed time, and a time-left guess once there's progress. */
function showProgress(audioSeconds) {
  const started = performance.now();
  let last = { stage: "queued", progress: null, stageSeconds: 0 };
  const bar = $("run-bar");

  const paint = () => {
    const elapsed = (performance.now() - started) / 1000;
    const { stage, progress, stageSeconds } = last;
    let detail = "";
    if (stage === "transcribing" && progress > 0.02) {
      const left = (stageSeconds * (1 - progress)) / progress;
      detail = ` ${Math.round(progress * 100)}%, about ${span(left)} left`;
    } else if (stage === "speakers" && audioSeconds) {
      detail = ` (usually about ${span(Math.max(2, audioSeconds / store.get("wsw:speed", DEFAULT_SPEED)))})`;
    }
    $("run-status-text").textContent = `${STAGE_LABELS[stage] ?? stage}…${detail} · ${span(elapsed)} so far`;
    const determinate = stage === "transcribing" && progress !== null;
    bar.classList.toggle("determinate", determinate);
    bar.style.setProperty("--p", `${Math.round((progress ?? 0) * 100)}%`);
  };

  paint();
  $("run-status").hidden = false;
  const timer = setInterval(paint, 250);
  return {
    update(next) { last = next; paint(); },
    stop() { clearInterval(timer); $("run-status").hidden = true; },
  };
}

// ---- results ----

function showResult(result) {
  state.result = result;
  state.names = store.get(namesKey(), {});
  audio.src = state.url;
  activeTurn = -1;

  renderSummary(result);
  $("mono-note").hidden = !(result.mono_source && result.channel !== "mix");
  $("results").classList.toggle("with-text", Boolean(result.transcript));
  timeline.render(result, { nameOf, colorOf });
  renderSpeakers($("speakers"), result, { names: state.names, colorOf, onRename: rename });
  const turns = shownTurns(result);
  $("turn-count").textContent = turns.length;
  renderTurns($("turns"), turns, { nameOf, colorOf, onPick: (t) => { seek(t.start); audio.play(); } });
  $("results").hidden = false;
  $("results").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderSummary(r) {
  const items = [
    ["Length", span(r.audio_seconds)],
    ["Speakers", Object.keys(r.speakers).length],
    ["Speakers found in", `${span(r.infer_seconds)} (${r.rtfx}×)`],
  ];
  if (r.transcript) {
    items.push(["Transcribed in", `${span(r.transcript.infer_seconds)} (${r.transcript.rtfx}×)`]);
    items.push(["Language", r.transcript.language.toUpperCase()]);
  }
  items.push(["Ran on", r.device.toUpperCase()]);
  $("summary").replaceChildren(...items.map(([k, v]) => {
    const div = document.createElement("div");
    div.append(Object.assign(document.createElement("dt"), { textContent: k }),
               Object.assign(document.createElement("dd"), { textContent: v }));
    return div;
  }));
}

function rename(speaker, value) {
  state.names[speaker] = value;
  store.set(namesKey(), state.names);
  for (const node of document.querySelectorAll(`[data-name-for="${speaker}"]`)) {
    node.textContent = nameOf(speaker);
  }
}

$("zoom").addEventListener("change", (e) => timeline.setZoom(Number(e.target.value)));
for (const btn of document.querySelectorAll("[data-export]")) {
  btn.addEventListener("click", () => download(btn.dataset.export, {
    result: state.result, turns: shownTurns(state.result), nameOf, fileName: state.file.name,
  }));
}

// ---- playback sync ----

let activeTurn = -1;

function seek(t) {
  audio.currentTime = Math.max(0, Math.min(t, state.result?.audio_seconds ?? t));
  syncToAudio();
}

function syncToAudio() {
  const r = state.result;
  if (!r) return;
  const t = audio.currentTime;
  const speaking = [...new Set(r.segments.filter((s) => s.start <= t && t < s.end).map((s) => s.speaker))];
  timeline.setTime(t, speaking, !audio.paused);

  for (const li of $("speakers").children) {
    li.classList.toggle("speaking", speaking.includes(Number(li.dataset.speaker)));
  }
  const idx = shownTurns(r).findIndex((turn) => turn.start <= t && t < turn.end);
  if (idx !== activeTurn) {
    $("turns").children[activeTurn]?.classList.remove("active");
    const li = $("turns").children[idx];
    li?.classList.add("active");
    if (li && !audio.paused && !$("turns").matches(":hover")) li.scrollIntoView({ block: "nearest" });
    activeTurn = idx;
  }
}

function loop() {
  syncToAudio();
  if (!audio.paused) requestAnimationFrame(loop);
}
audio.addEventListener("play", loop);
audio.addEventListener("seeked", syncToAudio);
audio.addEventListener("pause", syncToAudio);

document.addEventListener("keydown", (e) => {
  // Turn buttons stay in scope: Space after clicking a turn should pause, not replay it.
  const ownKeys = e.target.closest("input, select, textarea, audio, button:not(#turns button)");
  if (!state.result || ownKeys) return;
  if (e.key === " ") { e.preventDefault(); audio.paused ? audio.play() : audio.pause(); }
  if (e.key === "ArrowLeft") seek(audio.currentTime - 5);
  if (e.key === "ArrowRight") seek(audio.currentTime + 5);
});

// ---- errors ----

function showError(message) {
  $("error").textContent = message;
  $("error").hidden = false;
}
function hideError() { $("error").hidden = true; }

pollStatus();

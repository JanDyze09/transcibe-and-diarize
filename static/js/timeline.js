// One lane per speaker, a ruler, and a playhead. Click anywhere to seek.

import { clock } from "./format.js";

const NICE_STEPS = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600];
const MIN_TICK_PX = 84;

const el = (tag, className, attrs = {}) =>
  Object.assign(document.createElement(tag), className ? { className } : {}, attrs);

export function createTimeline(root, { onSeek }) {
  let duration = 1;
  let zoom = 1;
  let lanes = new Map();

  root.className = "tl";
  const labels = el("div", "tl-labels");
  const scroller = el("div", "tl-scroll");
  const canvas = el("div", "tl-canvas");
  const ruler = el("div", "tl-ruler");
  const playhead = el("div", "tl-playhead");
  scroller.append(canvas);
  root.append(labels, scroller);

  canvas.addEventListener("click", (e) => {
    const box = canvas.getBoundingClientRect();
    onSeek(((e.clientX - box.left) / box.width) * duration);
  });
  new ResizeObserver(() => drawRuler()).observe(scroller);

  function drawRuler() {
    const px = canvas.clientWidth || 1;
    const step = NICE_STEPS.find((s) => (s / duration) * px >= MIN_TICK_PX) ?? NICE_STEPS.at(-1);
    ruler.replaceChildren();
    for (let t = 0; t <= duration; t += step) {
      const tick = el("span", "tl-tick", { textContent: clock(t) });
      tick.style.left = `${(t / duration) * 100}%`;
      ruler.append(tick);
    }
  }

  function render(result, { nameOf, colorOf }) {
    duration = Math.max(result.audio_seconds, 0.1);
    lanes = new Map();
    labels.replaceChildren(el("div", "tl-label-spacer"));
    canvas.replaceChildren(ruler);

    for (const key of Object.keys(result.speakers)) {
      const speaker = Number(key);
      const label = el("div", "tl-label");
      label.style.setProperty("--c", colorOf(speaker));
      label.append(el("span", "swatch"), el("span", "tl-name", { textContent: nameOf(speaker) }));
      label.lastChild.dataset.nameFor = speaker;
      labels.append(label);

      const lane = el("div", "tl-lane");
      lane.style.setProperty("--c", colorOf(speaker));
      canvas.append(lane);
      lanes.set(speaker, { label, lane });
    }

    for (const seg of result.segments) {
      const block = el("span", "tl-block", { title: `${clock(seg.start)} – ${clock(seg.end)}` });
      block.style.left = `${(seg.start / duration) * 100}%`;
      block.style.width = `${((seg.end - seg.start) / duration) * 100}%`;
      lanes.get(seg.speaker)?.lane.append(block);
    }
    canvas.append(playhead);
    setZoom(zoom);
    setTime(0, []);
  }

  function setZoom(value) {
    const at = scroller.scrollLeft / (canvas.clientWidth || 1);
    zoom = value;
    canvas.style.width = `${zoom * 100}%`;
    scroller.scrollLeft = at * canvas.clientWidth;
    drawRuler();
  }

  /** Move the playhead; `speaking` lists speakers active right now. */
  function setTime(t, speaking, follow = false) {
    playhead.style.left = `${(t / duration) * 100}%`;
    for (const [speaker, { label, lane }] of lanes) {
      const on = speaking.includes(speaker);
      label.classList.toggle("speaking", on);
      lane.classList.toggle("speaking", on);
    }
    if (follow && zoom > 1) {
      const x = (t / duration) * canvas.clientWidth;
      const { scrollLeft, clientWidth } = scroller;
      if (x < scrollLeft || x > scrollLeft + clientWidth - 24) scroller.scrollLeft = x - clientWidth * 0.2;
    }
  }

  return { render, setZoom, setTime };
}

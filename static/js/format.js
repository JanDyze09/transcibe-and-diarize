// Time formatting shared by the page, the timeline and the exports.

const pad = (n, width = 2) => String(Math.floor(n)).padStart(width, "0");

/** 75.4 -> "1:15", 3725 -> "1:02:05" */
export function clock(seconds) {
  const s = Math.max(0, seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h ? `${h}:${pad(m)}:${pad(s % 60)}` : `${m}:${pad(s % 60)}`;
}

/** 75.4 -> "00:01:15,400" */
export function srtTime(seconds) {
  const ms = Math.round(seconds * 1000);
  return `${pad(ms / 3600000)}:${pad((ms / 60000) % 60)}:${pad((ms / 1000) % 60)},${pad(ms % 1000, 3)}`;
}

/** Human length: "3.4 s", "2 min 5 s", "1 h 3 min" */
export function span(seconds) {
  if (seconds < 60) return `${seconds < 10 ? seconds.toFixed(1) : Math.round(seconds)} s`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.round(seconds % 60);
  return h ? `${h} h ${m} min` : s ? `${m} min ${s} s` : `${m} min`;
}

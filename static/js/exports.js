// Turn a result into downloadable files, using the names the user gave.
// `turns` carry `text` when the run was transcribed; exports include it then.

import { clock, srtTime } from "./format.js";

const line = (t, nameOf) => (t.text ? `${nameOf(t.speaker)}: ${t.text}` : nameOf(t.speaker));

const builders = {
  srt: ({ turns, nameOf }) =>
    turns
      .map((t, i) => `${i + 1}\n${srtTime(t.start)} --> ${srtTime(t.end)}\n${line(t, nameOf)}\n`)
      .join("\n"),

  txt: ({ turns, nameOf }) =>
    turns.map((t) => `[${clock(t.start)}] ${line(t, nameOf)}`).join("\n") + "\n",

  rttm: ({ result, nameOf, base }) =>
    result.segments
      .map((s) => {
        const who = nameOf(s.speaker).replace(/\s+/g, "_");
        return `SPEAKER ${base} 1 ${s.start.toFixed(3)} ${(s.end - s.start).toFixed(3)} <NA> <NA> ${who} <NA> <NA>`;
      })
      .join("\n") + "\n",

  json: ({ result, nameOf }) => {
    const names = Object.fromEntries(Object.keys(result.speakers).map((k) => [k, nameOf(Number(k))]));
    return JSON.stringify({ ...result, names }, null, 2);
  },
};

const types = { srt: "application/x-subrip", txt: "text/plain", rttm: "text/plain", json: "application/json" };

export function download(kind, { result, turns, nameOf, fileName }) {
  const base = fileName.replace(/\.[^.]+$/, "") || "recording";
  const body = builders[kind]({ result, turns, nameOf, base });
  // BOM so Notepad and subtitle tools read Hebrew as UTF-8; JSON/RTTM parsers choke on one.
  const parts = kind === "srt" || kind === "txt" ? ["﻿", body] : [body];
  const url = URL.createObjectURL(new Blob(parts, { type: `${types[kind]};charset=utf-8` }));
  const a = Object.assign(document.createElement("a"), {
    href: url,
    download: `${base}.${result.channel}.${kind}`,
  });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// The speaker list (rename, talk share) and the turn list (click to play).

import { clock, span } from "./format.js";

const make = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

export function renderSpeakers(list, result, { names, colorOf, onRename }) {
  const total = Object.values(result.speakers).reduce((sum, s) => sum + s.seconds, 0) || 1;
  const rows = Object.entries(result.speakers)
    .sort(([, a], [, b]) => b.seconds - a.seconds)
    .map(([key, s]) => {
      const speaker = Number(key);
      const share = Math.round((s.seconds / total) * 100);
      const li = make("li");
      li.dataset.speaker = speaker;
      li.style.setProperty("--c", colorOf(speaker));
      li.style.setProperty("--share", `${(s.seconds / total) * 100}%`);

      const input = make("input", "name");
      input.value = names[speaker] ?? "";
      input.placeholder = `Speaker ${speaker + 1}`;
      input.spellcheck = false;
      input.setAttribute("aria-label", `Name for speaker ${speaker + 1}`);
      input.addEventListener("input", () => onRename(speaker, input.value));
      input.addEventListener("keydown", (e) => { if (e.key === "Enter") input.blur(); });

      const bar = make("span", "share");
      bar.append(make("span"));
      li.append(
        make("span", "swatch"),
        input,
        make("span", "talk", `${span(s.seconds)} · ${share}%`),
        bar,
        make("span", "turns-n", `${s.turns} turn${s.turns === 1 ? "" : "s"}`),
      );
      return li;
    });
  list.replaceChildren(...rows);
}

/** Turns carry `text` when the run included transcription. */
export function renderTurns(list, turns, { nameOf, colorOf, onPick }) {
  const rows = turns.map((t, i) => {
    const btn = make("button");
    btn.type = "button";
    btn.style.setProperty("--c", colorOf(t.speaker));
    const who = make("span", "who", nameOf(t.speaker));
    who.dataset.nameFor = t.speaker;
    btn.append(make("span", "at", clock(t.start)), make("span", "swatch"), who,
               make("span", "len", span(t.end - t.start)));
    if (t.text) {
      const text = make("span", "text", t.text);
      text.dir = "auto"; // Hebrew lines read right to left
      btn.append(text);
    }
    btn.addEventListener("click", () => onPick(t));
    const li = make("li");
    li.dataset.index = i;
    li.append(btn);
    return li;
  });
  list.replaceChildren(...rows);
}

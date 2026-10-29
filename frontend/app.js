const $ = (id) => document.getElementById(id);
const h = (tag, props = {}, ...kids) => {
  const el = Object.assign(document.createElement(tag), props);
  el.append(...kids.flat().filter((k) => k != null && k !== false && k !== ""));
  return el;
};

const nf = new Intl.NumberFormat("ru-RU");
const sf = new Intl.NumberFormat("ru-RU", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const pr = new Intl.PluralRules("ru-RU");
const plural = (n, one, few, many) => {
  const r = pr.select(n ?? 0);
  return `${nf.format(n ?? 0)} ${r === "one" ? one : r === "few" ? few : many}`;
};
const size = (b = 0) => (b < 1024 ? `${nf.format(b)} Б` : `${sf.format(b / 1024)} КБ`);
const sec = (ms = 0) => `${sf.format(ms / 1000)} с`;
const clock = (s) => (s < 60 ? `${s} с` : `${Math.floor(s / 60)} мин ${String(s % 60).padStart(2, "0")} с`);
const smooth = () => (matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth");
const rich = (text = "") => String(text).split("`").map((p, i) => (i % 2 ? h("code", { textContent: p }) : p));

const SEV = { bug: ["Баг", 0], warning: ["Предупреждение", 1], nit: ["Мелочь", 2] };
const sevKey = (s) => (s in SEV ? s : "nit");
const KINDS = { thought: "Мысль", tool_call: "Вызов инструмента", tool_result: "Результат", conclusion: "Вывод" };
const HINTS = [
  "Передаю файл агенту",
  "ruff проверяет стиль и типичные ошибки",
  "ty проверяет типы",
  "Агент читает код и сверяет его с выводом линтеров",
  "Ищу неверные условия и границы",
  "Проверяю обработку исключений",
  "Сверяю сигнатуры функций и их вызовы",
  "Смотрю, закрываются ли файлы и соединения",
  "Собираю находки в ревью",
];
const FALLBACK = {
  400: "Этот файл не подходит для проверки.",
  413: "Файл больше допустимого размера.",
  422: "Файл не в кодировке UTF-8. Пересохраните его в UTF-8 и отправьте снова.",
  502: "Модель сейчас не отвечает. Попробуйте через минуту.",
  504: "Анализ не уложился в отведённое время. Попробуйте файл поменьше.",
};
const VIEWS = { notice: ["error"], drop: ["empty", "error"], progress: ["sending"], result: ["result"] };

const config = { maxBytes: 200000, model: null };
let report = null;
let rows = [];
let controller = null;
let ticker = null;

const announce = (text) => ($("live").textContent = text);

function setState(state) {
  document.body.dataset.state = state;
  for (const [id, states] of Object.entries(VIEWS)) $(id).hidden = !states.includes(state);
}

function paintConfig() {
  $("limit").textContent = size(config.maxBytes);
  $("foot-model").textContent = config.model ? `Модель: ${config.model}` : "";
}

function fail(message, code = "") {
  stopProgress();
  $("notice-text").textContent = message;
  $("notice-code").textContent = code;
  setState("error");
  $("drop").focus();
}

function problemOf(files) {
  if (files.length === 0) return "Нужен файл с расширением .py.";
  if (files.length > 1) return `Перетащено ${plural(files.length, "файл", "файла", "файлов")}, а проверяется один за раз. Выберите один файл .py.`;
  const [file] = files;
  if (!file.name) return "У файла нет имени. Сохраните его как .py и попробуйте снова.";
  if (!file.name.toLowerCase().endsWith(".py")) return `«${file.name}» не Python-файл. Нужен файл с расширением .py.`;
  if (file.size > config.maxBytes) return `«${file.name}» весит ${size(file.size)}, а предел ${size(config.maxBytes)}.`;
  return null;
}

async function take(list) {
  if (controller) return;
  const files = [...(list ?? [])];
  const problem = problemOf(files);
  if (problem) return fail(problem, "Файл не отправлен");
  const [file] = files;
  controller = new AbortController();
  try {
    const text = await file.text();
    startProgress(file.name, file.size, text);
    const body = new FormData();
    body.append("file", file, file.name);
    const res = await fetch("/api/v1/review", { method: "POST", body, signal: controller.signal });
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      const code = data?.error?.code;
      return fail(data?.error?.message ?? FALLBACK[res.status] ?? "Сервер не смог проверить файл.", code ? `${code}, HTTP ${res.status}` : `HTTP ${res.status}`);
    }
    if (!data?.review) return fail("Сервер прислал ответ, который страница не может прочитать.", `HTTP ${res.status}`);
    render(data, text);
  } catch (e) {
    if (e.name !== "AbortError") return fail("Сервер недоступен. Проверьте, что бэкенд запущен, и отправьте файл ещё раз.", "network");
    stopProgress();
    setState("empty");
    announce("Проверка отменена.");
  } finally {
    controller = null;
  }
}

function startProgress(name, bytes, text) {
  $("progress-file").textContent = name;
  $("progress-meta").textContent = `${size(bytes)}, ${plural(lineCount(text), "строка", "строки", "строк")}`;
  buildCode($("scan"), text.split(/\r\n|\r|\n/).slice(0, 60).join("\n"));
  const started = Date.now();
  const tick = () => {
    const s = Math.floor((Date.now() - started) / 1000);
    $("elapsed").textContent = clock(s);
    const i = s < 21 ? Math.floor(s / 7) : 3 + (Math.floor((s - 21) / 7) % (HINTS.length - 3));
    $("hint").textContent = HINTS[i];
  };
  tick();
  clearInterval(ticker);
  ticker = setInterval(tick, 1000);
  setState("sending");
  announce(`Отправляю ${name} на ревью.`);
}

function stopProgress() {
  clearInterval(ticker);
  ticker = null;
}

function lineCount(text) {
  const lines = text.split(/\r\n|\r|\n/);
  return lines.at(-1) === "" ? lines.length - 1 : lines.length;
}

function buildCode(box, text, findings = [], lint = []) {
  const lines = text.split(/\r\n|\r|\n/);
  if (lines.length > 1 && lines.at(-1) === "") lines.pop();
  const sev = new Map();
  const notes = new Map();
  const note = (n, s) => notes.set(n, [...(notes.get(n) ?? []), s]);
  for (const f of findings) {
    for (let n = f.line; n <= Math.min(Math.max(f.end_line ?? f.line, f.line), lines.length); n++) {
      const k = sevKey(f.severity);
      if (!sev.has(n) || SEV[k][1] < SEV[sev.get(n)][1]) sev.set(n, k);
      note(n, `${SEV[k][0]}: ${f.title}`);
    }
  }
  for (const l of lint) note(l.line, `${l.tool} ${l.code}: ${l.message}`);
  const linted = new Set(lint.map((l) => l.line));
  box.style.setProperty("--digits", String(lines.length).length);
  box.replaceChildren(
    h("div", { className: "rows" }, lines.map((t, i) => h(
      "div",
      {
        className: ["ln", sev.has(i + 1) && `marked sev-${sev.get(i + 1)}`, linted.has(i + 1) && "has-lint"].filter(Boolean).join(" "),
        title: notes.get(i + 1)?.join("\n") ?? "",
      },
      h("span", { className: "no", textContent: i + 1 }),
      h("span", { className: "tx", textContent: t || " " }),
    ))),
  );
  return [...box.firstChild.children];
}

function jump(from, to, source) {
  const first = rows[from - 1];
  if (!first) return;
  const box = $("code");
  box.scrollTo({ top: first.offsetTop - box.clientHeight / 3, behavior: smooth() });
  $("code-panel").scrollIntoView({ block: "nearest", behavior: smooth() });
  for (const row of rows.slice(from - 1, Math.max(to ?? from, from))) {
    row.classList.remove("flash");
    void row.offsetWidth;
    row.classList.add("flash");
  }
  document.querySelectorAll(".is-active").forEach((el) => el.classList.remove("is-active"));
  source?.classList.add("is-active");
}

const range = (f) => (f.end_line && f.end_line > f.line ? `строки ${f.line}–${f.end_line}` : `строка ${f.line}`);

function findingEl(f) {
  const key = sevKey(f.severity);
  const li = h("li", { className: `finding sev-${key}` });
  li.append(...[
    h(
      "button",
      { className: "finding-head", type: "button", onclick: () => jump(f.line, f.end_line, li) },
      h("span", { className: "sev", textContent: SEV[key][0] }),
      h("span", { className: "where", textContent: range(f) }),
      h("span", { className: "finding-title", textContent: f.title ?? "" }),
    ),
    h("p", { className: "detail" }, rich(f.detail)),
    f.suggestion && h("div", { className: "suggestion" }, h("p", { textContent: "Как исправить" }), h("pre", {}, h("code", { textContent: f.suggestion }))),
  ].filter(Boolean));
  return li;
}

function lintEl(lint) {
  if (!lint.length) return h("p", { className: "empty", textContent: "Линтеры ничего не нашли." });
  return [...Map.groupBy(lint, (l) => l.tool)].map(([tool, items]) => h(
    "div",
    { className: "lint-group" },
    h("h3", { className: "lint-tool" }, h("code", { textContent: tool }), h("span", { className: "count", textContent: items.length })),
    h("ul", {}, items.map((l) => {
      const li = h("li");
      li.append(h(
        "button",
        { className: "lint-row", type: "button", onclick: () => jump(l.line, l.line, li) },
        h("code", { className: "lint-code", textContent: l.code }),
        h("span", { className: "pos", textContent: `${l.line}:${l.column}` }),
        h("span", { className: "msg" }, rich(l.message)),
      ));
      return li;
    })),
  ));
}

function outputEl(text = "") {
  const n = lineCount(text);
  const pre = h("pre", { className: "step-out", textContent: text || "пустой вывод" });
  if (text.length < 480 && n <= 8) return pre;
  return h("details", { className: "out" }, h("summary", { textContent: `Показать вывод, ${plural(n, "строка", "строки", "строк")}` }), pre);
}

function stepEl(s) {
  const kind = s.kind in KINDS ? s.kind : "thought";
  return h(
    "li",
    { className: `step k-${kind}` },
    h(
      "div",
      { className: "step-head" },
      h("span", { className: "step-kind", textContent: KINDS[kind] }),
      s.tool && h("code", { className: "step-tool", textContent: s.tool }),
      s.truncated && h("span", { className: "tag", textContent: "обрезано" }),
      h("span", { className: "step-time", textContent: `+${sec(s.at_ms)}` }),
    ),
    kind === "tool_call"
      ? h("pre", { className: "step-args", textContent: JSON.stringify(s.args ?? {}) })
      : kind === "tool_result"
        ? outputEl(s.text)
        : h("p", { className: "step-text" }, rich(s.text)),
  );
}

function usageText({ model = {}, usage = {} }) {
  return [
    model.name,
    plural(usage.tokens, "токен", "токена", "токенов"),
    plural(usage.tool_calls, "вызов инструмента", "вызова инструментов", "вызовов инструментов"),
    sec(usage.duration_ms),
  ].filter(Boolean).join(", ");
}

function render(data, text) {
  stopProgress();
  report = data;
  const { file = {}, review = {}, lint = [], reasoning = [], usage = {} } = data;
  const findings = review.findings ?? [];
  const worst = findings.map((f) => sevKey(f.severity)).sort((a, b) => SEV[a][1] - SEV[b][1])[0];
  $("r-name").textContent = file.name ?? "";
  $("code-name").textContent = file.name ?? "";
  $("r-meta").textContent = `${size(file.bytes)}, ${plural(file.lines, "строка", "строки", "строк")}`;
  const ok = review.verdict === "ok";
  $("r-verdict").textContent = ok ? "Замечаний нет" : "Есть замечания";
  $("r-verdict").className = `verdict ${ok ? "is-ok" : `sev-${worst ?? "warning"}`}`;
  $("r-summary").replaceChildren(...rich(review.summary));
  $("r-notes").replaceChildren(...[
    usage.truncated && h("p", { className: "note", textContent: "Анализ остановлен по пределу вызовов инструментов, поэтому ревью может быть неполным." }),
    review.dropped > 0 && h("p", { className: "note", textContent: `Не показано находок: ${nf.format(review.dropped)} — без строки в файле или сверх предела.` }),
  ].filter(Boolean));
  $("c-findings").textContent = findings.length;
  $("findings").replaceChildren(...(findings.length ? findings.map(findingEl) : [h("li", { className: "empty", textContent: "Логических ошибок агент не нашёл." })]));
  $("c-lint").textContent = lint.length;
  $("lint").replaceChildren(...[lintEl(lint)].flat());
  $("c-reasoning").textContent = `${plural(reasoning.length, "шаг", "шага", "шагов")}, ${sec(usage.duration_ms)}`;
  $("reasoning").replaceChildren(...reasoning.map(stepEl));
  $("reasoning-box").open = matchMedia("(min-width: 1000px)").matches;
  $("usage").textContent = usageText(data);
  rows = buildCode($("code"), text, findings, lint);
  $("code").scrollTop = 0;
  setState("result");
  window.scrollTo({ top: 0 });
  $("r-name").focus({ preventScroll: true });
  announce(`Ревью готово: ${plural(findings.length, "находка", "находки", "находок")}, линтеры: ${lint.length}.`);
}

function markdown() {
  const { file = {}, review = {}, lint = [] } = report;
  const out = [`# Ревью ${file.name}`, "", `**Вердикт:** ${review.verdict === "ok" ? "замечаний нет" : "есть замечания"}`, "", review.summary ?? "", ""];
  const findings = review.findings ?? [];
  if (findings.length) out.push("## Находки", "");
  findings.forEach((f, i) => {
    out.push(`### ${i + 1}. ${SEV[sevKey(f.severity)][0]}: ${f.title} (${range(f)})`, "", f.detail ?? "", "");
    if (f.suggestion) out.push("```python", f.suggestion, "```", "");
  });
  if (lint.length) out.push("## Линтеры", "", ...lint.map((l) => `- ${l.tool} \`${l.code}\` ${l.line}:${l.column} ${l.message}`), "");
  out.push(`_${usageText(report)}_`, "");
  return out.join("\n");
}

async function copy() {
  const text = markdown();
  let ok = true;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = h("textarea", { value: text, className: "sr-only" });
    document.body.append(ta);
    ta.select();
    ok = document.execCommand("copy");
    ta.remove();
  }
  const btn = $("copy");
  btn.textContent = ok ? "Скопировано" : "Не удалось скопировать";
  announce(btn.textContent);
  setTimeout(() => (btn.textContent = "Скопировать как Markdown"), 2000);
}

function reset() {
  report = null;
  rows = [];
  $("code").replaceChildren();
  $("file").value = "";
  setState("empty");
  $("drop").focus();
}

const pick = () => !controller && $("file").click();
$("drop").addEventListener("click", pick);
$("drop").addEventListener("keydown", (e) => {
  if (e.key !== "Enter" && e.key !== " ") return;
  e.preventDefault();
  pick();
});
$("file").addEventListener("change", (e) => take(e.target.files));
$("cancel").addEventListener("click", () => (controller ? controller.abort() : (stopProgress(), setState("empty"))));
$("again").addEventListener("click", reset);
$("copy").addEventListener("click", copy);

let depth = 0;
const hasFiles = (e) => e.dataTransfer?.types?.includes("Files");
const dragging = (on) => document.body.classList.toggle("dragging", on && !controller);
document.addEventListener("dragenter", (e) => hasFiles(e) && (depth++, dragging(true)));
document.addEventListener("dragleave", (e) => hasFiles(e) && --depth <= 0 && ((depth = 0), dragging(false)));
document.addEventListener("dragover", (e) => {
  e.preventDefault();
  if (e.dataTransfer) e.dataTransfer.dropEffect = controller ? "none" : "copy";
});
document.addEventListener("drop", (e) => {
  e.preventDefault();
  depth = 0;
  dragging(false);
  if (hasFiles(e)) take(e.dataTransfer.files);
});

async function boot() {
  const demo = new URLSearchParams(location.search).get("demo");
  if (demo === null) {
    try {
      const res = await fetch("/api/v1/config");
      const c = res.ok ? await res.json() : {};
      config.maxBytes = c.limits?.max_file_bytes ?? config.maxBytes;
      config.model = c.model?.name ?? null;
    } catch {
      config.model = null;
    }
    return paintConfig();
  }
  try {
    const data = await (await fetch("fixtures/sample-response.json")).json();
    config.model = data.model?.name ?? null;
    paintConfig();
    if (demo === "progress") return startProgress(data.file.name, data.file.bytes, data.demo_source);
    render(data, data.demo_source ?? "");
  } catch {
    fail("Демо-ответ не загрузился: нет файла fixtures/sample-response.json.", "demo");
  }
}

boot();

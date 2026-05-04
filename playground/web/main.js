import { initEngine, execute, reset, snapshotKey, listKeys } from "./engine.js";
import { buildForm, collectArgs } from "./ui.js";

const $ = (sel) => document.querySelector(sel);

const state = {
  commands: {},
  selected: null,
};

async function start() {
  // Load JSON spec
  const json = await fetch("commands.json").then(r => r.json());
  state.commands = json;
  populateSidebar();

  // Boot WASM
  try {
    await initEngine();
    $("#wasm-status-dot").classList.add("ready");
    $("#wasm-status").textContent = "WASM ready";
    const sz = await fetch("redis_array.wasm").then(r => r.blob()).then(b => b.size);
    $("#wasm-size").textContent = `${(sz / 1024).toFixed(1)} KB`;
  } catch (e) {
    $("#wasm-status-dot").classList.add("error");
    $("#wasm-status").textContent = "WASM error";
    appendOutput(`failed to load WASM: ${e.message}`, "err");
    return;
  }

  // Wire buttons
  $("#run-btn").addEventListener("click", runCurrent);
  $("#clear-btn").addEventListener("click", () => {
    if (state.selected) selectCommand(state.selected);
  });
  $("#reset-db").addEventListener("click", () => {
    reset();
    refreshState();
    appendOutput("FLUSHALL (local)", "cmd");
    appendOutput("OK", "ok");
  });

  // Auto-select first
  selectCommand(Object.keys(state.commands)[0]);

  // Live preview as user types
  document.addEventListener("input", (e) => {
    if (e.target.closest("#cmd-form")) updatePreview();
  });
  document.addEventListener("change", (e) => {
    if (e.target.closest("#cmd-form")) updatePreview();
  });
}

function populateSidebar() {
  const list = $("#command-list");
  list.innerHTML = "";
  for (const [name, spec] of Object.entries(state.commands)) {
    const li = document.createElement("li");
    li.dataset.name = name;
    const n = document.createElement("span");
    n.className = "name";
    n.textContent = name;
    const s = document.createElement("span");
    s.className = "summary";
    s.textContent = spec.summary || "";
    li.append(n, s);
    li.addEventListener("click", () => selectCommand(name));
    list.appendChild(li);
  }
}

function selectCommand(name) {
  state.selected = name;
  const spec = state.commands[name];
  for (const li of document.querySelectorAll("#command-list li")) {
    li.classList.toggle("active", li.dataset.name === name);
  }
  renderDocs(name, spec);
  $("#form-panel").hidden = false;
  buildForm($("#cmd-form"), spec);
  updatePreview();
}

function renderDocs(name, spec) {
  const docs = $("#docs");
  docs.innerHTML = "";
  const h = document.createElement("h2");
  h.textContent = name;
  const summary = document.createElement("p");
  summary.textContent = spec.summary || "";
  const syntax = document.createElement("div");
  syntax.className = "syntax";
  syntax.textContent = renderSyntax(name, spec);

  const meta = document.createElement("div");
  meta.className = "meta";
  if (spec.complexity) {
    const c = pill("complexity", spec.complexity);
    meta.appendChild(c);
  }
  if (spec.since) meta.appendChild(pill("since", spec.since));
  if (spec.command_flags) {
    for (const f of spec.command_flags) meta.appendChild(pill("", f));
  }
  if (spec.acl_categories) {
    for (const f of spec.acl_categories) meta.appendChild(pill("acl", f));
  }

  docs.append(h, summary, syntax, meta);

  if (spec.arguments) {
    const args = document.createElement("div");
    args.className = "args";
    args.innerHTML = `<h4>Arguments</h4>`;
    args.appendChild(renderArgList(spec.arguments));
    docs.appendChild(args);
  }

  if (spec.reply_schema) {
    const reply = document.createElement("div");
    reply.className = "reply";
    reply.innerHTML = `<h4>Reply</h4>`;
    const desc = describeReply(spec.reply_schema);
    if (desc) {
      const p = document.createElement("p");
      p.style.margin = "0 0 6px";
      p.style.fontSize = "13px";
      p.textContent = desc;
      reply.appendChild(p);
    }
    const pre = document.createElement("pre");
    pre.textContent = JSON.stringify(spec.reply_schema, null, 2);
    reply.appendChild(pre);
    docs.appendChild(reply);
  }
}

function pill(kind, text) {
  const p = document.createElement("span");
  p.className = "pill";
  p.textContent = kind ? `${kind}: ${text}` : text;
  return p;
}

function describeReply(schema) {
  if (!schema) return null;
  if (schema.description) return schema.description;
  if (schema.oneOf) {
    return schema.oneOf.map(o => o.description).filter(Boolean).join(" / ");
  }
  return null;
}

function renderArgList(args, depth = 0) {
  const ul = document.createElement("ul");
  ul.className = "arglist";
  for (const a of args) {
    const li = document.createElement("li");
    let label = `<code>${a.name}</code> <span style="color:var(--muted)">${a.type}${a.multiple ? "[]" : ""}${a.optional ? " (optional)" : ""}</span>`;
    if (a.token) label += ` <code>${a.token}</code>`;
    li.innerHTML = label;
    if (a.arguments) li.appendChild(renderArgList(a.arguments, depth + 1));
    ul.appendChild(li);
  }
  return ul;
}

/* Build a Redis-style syntax line, e.g. `ARGREP key start end EXACT|MATCH|GLOB|RE pattern [LIMIT count]` */
function renderSyntax(name, spec) {
  const parts = [name];
  for (const a of (spec.arguments || [])) parts.push(syntaxFor(a));
  return parts.join(" ");
}

function syntaxFor(a) {
  let core;
  if (a.type === "pure-token") core = a.token || a.name.toUpperCase();
  else if (a.type === "oneof") {
    const opts = (a.arguments || []).map(syntaxFor);
    core = opts.join(" | ");
    if (opts.length > 1) core = `(${core})`;
  } else if (a.type === "block") {
    const subs = (a.arguments || []).map(syntaxFor).join(" ");
    core = subs;
  } else if (a.type === "key") core = `key`;
  else core = a.name;
  if (a.token && a.type !== "pure-token") core = `${a.token} ${core}`;
  if (a.multiple) core = `${core} [${core} ...]`;
  if (a.optional) core = `[${core}]`;
  return core;
}

/* ---------- run ---------- */

function updatePreview() {
  if (!state.selected) return;
  const args = collectArgs($("#cmd-form"));
  const cmd = [state.selected, ...args].join(" ");
  $("#cmd-preview").textContent = cmd;
}

function runCurrent() {
  if (!state.selected) return;
  const args = collectArgs($("#cmd-form"));
  appendOutput(`> ${state.selected} ${args.map(quoteIfNeeded).join(" ")}`, "cmd");
  const reply = execute(state.selected, args);
  renderReply(reply);
  refreshState();
}

function quoteIfNeeded(s) {
  if (/[\s"']/.test(s) || s === "") return JSON.stringify(s);
  return s;
}

function renderReply(r, indent = 0) {
  const pad = "  ".repeat(indent);
  switch (r.type) {
    case "error":
      appendOutput(`${pad}(error) ${r.value}`, "err");
      break;
    case "integer":
      appendOutput(`${pad}(integer) ${r.value}`, "num");
      break;
    case "bulk":
      appendOutput(`${pad}"${r.value}"`, "ok");
      break;
    case "nil":
      appendOutput(`${pad}(nil)`, "nil");
      break;
    case "array":
      if (r.value.length === 0) {
        appendOutput(`${pad}(empty array)`, "ok");
      } else {
        for (let i = 0; i < r.value.length; i++) {
          appendOutput(`${pad}${i + 1}) `, "ts", false);
          // print inline
          renderInline(r.value[i]);
        }
      }
      break;
    case "map":
      if (r.value.length === 0) appendOutput(`${pad}(empty map)`, "ok");
      else {
        for (const [k, v] of r.value) {
          appendOutput(`${pad}${k} `, "ts", false);
          renderInline(v);
        }
      }
      break;
  }
}

function renderInline(r) {
  switch (r.type) {
    case "integer": appendOutput(`(integer) ${r.value}`, "num"); break;
    case "bulk":    appendOutput(`"${r.value}"`, "ok"); break;
    case "nil":     appendOutput(`(nil)`, "nil"); break;
    case "error":   appendOutput(`(error) ${r.value}`, "err"); break;
    default:        appendOutput(JSON.stringify(r.value), "ok"); break;
  }
}

function appendOutput(text, cls = "ok", newline = true) {
  const out = $("#output");
  const span = document.createElement("span");
  span.className = cls;
  span.textContent = text + (newline ? "\n" : "");
  out.appendChild(span);
  out.scrollTop = out.scrollHeight;
}

function refreshState() {
  const view = $("#state-view");
  view.innerHTML = "";
  const keys = listKeys();
  if (keys.length === 0) {
    view.innerHTML = '<em>(no keys yet — try <code>ARSET myarr 0 hello world</code>)</em>';
    return;
  }
  for (const { name } of keys) {
    const snap = snapshotKey(name, 50);
    const card = document.createElement("div");
    card.className = "key";
    const h = document.createElement("h4");
    const nm = document.createElement("span");
    nm.className = "name";
    nm.textContent = name;
    const meta = document.createElement("span");
    meta.className = "meta";
    const insertDisplay = snap.insert_idx === -1n ? "—" : snap.insert_idx.toString();
    meta.textContent = `count=${snap.count} len=${snap.len} insert_idx=${insertDisplay}`;
    h.append(nm, meta);
    card.appendChild(h);

    if (snap.items.length === 0) {
      const em = document.createElement("em");
      em.textContent = "(empty)";
      card.appendChild(em);
    } else {
      const tbl = document.createElement("table");
      const head = document.createElement("tr");
      head.innerHTML = `<th>index</th><th>value</th>`;
      tbl.appendChild(head);
      for (const item of snap.items) {
        const tr = document.createElement("tr");
        const td1 = document.createElement("td");
        td1.className = "idx";
        td1.textContent = item.idx.toString();
        const td2 = document.createElement("td");
        if (item.value === null) {
          td2.className = "gap";
          td2.textContent = "(empty)";
        } else {
          td2.textContent = item.value;
        }
        tr.append(td1, td2);
        tbl.appendChild(tr);
      }
      card.appendChild(tbl);
      if (snap.truncated) {
        const more = document.createElement("p");
        more.style.fontSize = "11.5px";
        more.style.color = "var(--muted)";
        more.style.margin = "6px 0 0";
        more.textContent = `(showing first 50 of len=${snap.len})`;
        card.appendChild(more);
      }
    }
    view.appendChild(card);
  }
}

start();

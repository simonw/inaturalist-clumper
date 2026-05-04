/*
 * Build dynamic forms from a Redis-style command JSON spec.
 *
 * Spec argument types we support:
 *   - "key", "string", "integer"            -> single text/number input
 *   - "pure-token"                          -> a button-toggle for the keyword
 *   - "block" (optional `multiple`)         -> nested fieldset, possibly repeating
 *   - "oneof" (optional `multiple`)         -> a chooser; if `multiple`, repeating
 *
 * Each argument may have:
 *   - optional: true -> can be omitted
 *   - multiple: true -> repeats (1+ instances or 0+ if also optional)
 *   - token: "FOO"   -> keyword that must be emitted before the value
 */

export function buildForm(formEl, spec) {
  formEl.innerHTML = "";
  const ctx = { args: spec.arguments || [] };
  for (const arg of ctx.args) {
    formEl.appendChild(renderArg(arg));
  }
}

function renderArg(arg) {
  const wrap = document.createElement("div");
  wrap.className = "form-row";
  wrap.dataset.argName = arg.name;
  wrap.dataset.argType = arg.type;
  if (arg.optional) wrap.dataset.optional = "1";
  if (arg.multiple) wrap.dataset.multiple = "1";
  if (arg.token) wrap.dataset.token = arg.token;

  const label = document.createElement("label");
  label.className = "toplabel";
  label.textContent = arg.name;
  const ty = document.createElement("span");
  ty.className = "type";
  ty.textContent = arg.type + (arg.multiple ? "[]" : "");
  label.appendChild(ty);
  if (arg.optional) {
    const opt = document.createElement("span");
    opt.className = "opt";
    opt.textContent = "optional";
    label.appendChild(opt);
  }
  if (arg.token) {
    const tok = document.createElement("span");
    tok.className = "type";
    tok.textContent = arg.token;
    label.appendChild(tok);
  }

  if (arg.type === "pure-token") {
    // A toggle for whether to include the keyword.
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.dataset.tokenValue = arg.token || arg.name.toUpperCase();
    cb.id = `tok-${Math.random().toString(36).slice(2, 8)}`;
    const lab = document.createElement("label");
    lab.htmlFor = cb.id;
    lab.textContent = ` Include ${arg.token || arg.name.toUpperCase()}`;
    const row = document.createElement("div");
    row.className = "toggle-row";
    row.append(cb, lab);
    wrap.append(label, row);
    return wrap;
  }

  if (arg.type === "block" && arg.multiple) {
    wrap.append(label, renderRepeatedBlock(arg));
    return wrap;
  }
  if (arg.type === "block") {
    wrap.append(label, renderBlockBody(arg));
    return wrap;
  }
  if (arg.type === "oneof") {
    wrap.append(label, renderOneOf(arg));
    return wrap;
  }
  if (arg.multiple) {
    wrap.append(label, renderRepeatedScalar(arg));
    return wrap;
  }

  // scalar
  wrap.append(label, renderScalar(arg));
  return wrap;
}

function renderScalar(arg) {
  const inp = document.createElement("input");
  inp.type = arg.type === "integer" ? "text" : "text"; // text so we can pass big ints
  inp.placeholder = placeholderFor(arg);
  inp.dataset.kind = "scalar";
  inp.dataset.argType = arg.type;
  return inp;
}

function placeholderFor(arg) {
  if (arg.name === "key") return "myarr";
  if (arg.type === "integer") return arg.name;
  return arg.name;
}

function renderRepeatedScalar(arg) {
  const list = document.createElement("div");
  list.className = "repeated";
  list.dataset.kind = "repeated-scalar";
  const items = document.createElement("div");
  items.className = "items";
  list.appendChild(items);
  const addItem = () => {
    const row = document.createElement("div");
    row.className = "item";
    const inp = document.createElement("input");
    inp.type = "text";
    inp.placeholder = arg.name;
    inp.dataset.argType = arg.type;
    const rm = document.createElement("button");
    rm.type = "button";
    rm.className = "remove";
    rm.textContent = "×";
    rm.title = "remove";
    rm.onclick = () => row.remove();
    row.append(inp, rm);
    items.appendChild(row);
  };
  addItem();
  if (!arg.optional) {/* keep at least one */}
  const add = document.createElement("button");
  add.type = "button";
  add.className = "add";
  add.textContent = "+ add";
  add.onclick = addItem;
  list.appendChild(add);
  return list;
}

function renderBlockBody(arg) {
  const block = document.createElement("div");
  block.className = "block";
  block.dataset.kind = "block";
  for (const child of (arg.arguments || [])) {
    block.appendChild(renderArg(child));
  }
  return block;
}

function renderRepeatedBlock(arg) {
  const list = document.createElement("div");
  list.className = "repeated";
  list.dataset.kind = "repeated-block";
  const items = document.createElement("div");
  items.className = "items";
  list.appendChild(items);

  const addItem = () => {
    const row = document.createElement("div");
    row.className = "item";
    const inner = renderBlockBody(arg);
    inner.style.flex = "1";
    const rm = document.createElement("button");
    rm.type = "button";
    rm.className = "remove";
    rm.textContent = "×";
    rm.onclick = () => row.remove();
    row.append(inner, rm);
    items.appendChild(row);
  };
  addItem();
  const add = document.createElement("button");
  add.type = "button";
  add.className = "add";
  add.textContent = "+ add";
  add.onclick = addItem;
  list.appendChild(add);
  return list;
}

function renderOneOf(arg) {
  const wrap = document.createElement("div");
  wrap.className = "oneof";
  wrap.dataset.kind = "oneof";

  const choices = (arg.arguments || []);

  const renderChoice = () => {
    const row = document.createElement("div");
    row.className = "oneof-row";
    const sel = document.createElement("select");
    sel.className = "choose";
    for (const ch of choices) {
      const opt = document.createElement("option");
      opt.value = ch.name;
      const lbl = ch.token ? ch.token : ch.name.toUpperCase();
      opt.textContent = lbl;
      sel.appendChild(opt);
    }
    const argsHost = document.createElement("div");
    argsHost.className = "oneof-args";
    const renderInputs = () => {
      argsHost.innerHTML = "";
      const ch = choices.find(c => c.name === sel.value);
      if (!ch) return;
      if (ch.type === "pure-token") {
        const sp = document.createElement("span");
        sp.style.color = "var(--muted)";
        sp.style.fontSize = "12px";
        sp.textContent = "(no value)";
        argsHost.appendChild(sp);
      } else if (ch.type === "block") {
        for (const sub of (ch.arguments || [])) {
          if (sub.type === "pure-token") continue;
          const inp = document.createElement("input");
          inp.type = "text";
          inp.placeholder = sub.name;
          inp.dataset.argType = sub.type;
          inp.dataset.subName = sub.name;
          argsHost.appendChild(inp);
        }
      } else {
        const inp = document.createElement("input");
        inp.type = "text";
        inp.placeholder = ch.name;
        inp.dataset.argType = ch.type;
        argsHost.appendChild(inp);
      }
    };
    sel.addEventListener("change", renderInputs);
    renderInputs();
    row.append(sel, argsHost);
    if (arg.multiple) {
      const rm = document.createElement("button");
      rm.type = "button";
      rm.className = "remove";
      rm.textContent = "×";
      rm.onclick = () => row.remove();
      row.appendChild(rm);
    }
    return row;
  };

  const items = document.createElement("div");
  items.className = "items";
  // Optional oneofs start empty; required oneofs need at least one row.
  if (!arg.optional) items.appendChild(renderChoice());
  wrap.appendChild(items);

  if (arg.multiple || arg.optional) {
    const add = document.createElement("button");
    add.type = "button";
    add.className = "add";
    add.textContent = "+ add";
    add.onclick = () => items.appendChild(renderChoice());
    wrap.appendChild(add);
  }

  return wrap;
}

/* ----------- collect form into args list ----------- */

export function collectArgs(formEl) {
  const out = [];
  for (const child of formEl.children) {
    collectArg(child, out);
  }
  return out;
}

function collectArg(node, out) {
  const argName = node.dataset.argName;
  const argType = node.dataset.argType;
  const optional = node.dataset.optional === "1";
  const multiple = node.dataset.multiple === "1";
  const token = node.dataset.token;

  if (argType === "pure-token") {
    const cb = node.querySelector('input[type=checkbox]');
    if (cb && cb.checked) out.push(cb.dataset.tokenValue);
    return;
  }

  if (argType === "block" && multiple) {
    const items = node.querySelector('[data-kind="repeated-block"] .items');
    for (const item of items.children) {
      const inner = item.querySelector('.block');
      collectBlock(inner, out);
    }
    return;
  }

  if (argType === "block") {
    const inner = node.querySelector('.block');
    if (token) out.push(token);
    collectBlock(inner, out);
    return;
  }

  if (argType === "oneof") {
    const items = node.querySelector('[data-kind="oneof"] .items');
    for (const row of items.children) {
      const sel = row.querySelector("select.choose");
      const choiceName = sel.value;
      const argsHost = row.querySelector(".oneof-args");
      // Find choice spec by walking the form data — encode token from select label
      const tokLabel = sel.options[sel.selectedIndex].textContent;
      out.push(tokLabel);
      const inputs = argsHost.querySelectorAll("input");
      for (const inp of inputs) {
        const v = inp.value.trim();
        if (v) out.push(v);
      }
    }
    return;
  }

  if (multiple) {
    if (token) out.push(token);
    const items = node.querySelector('[data-kind="repeated-scalar"] .items');
    for (const item of items.children) {
      const inp = item.querySelector("input");
      const v = inp.value;
      if (v !== "") out.push(v);
    }
    return;
  }

  // scalar
  const inp = node.querySelector('input[data-kind=scalar]');
  if (!inp) return;
  const v = inp.value;
  if (v === "" && optional) return;
  if (token) out.push(token);
  out.push(v);
}

function collectBlock(blockEl, out) {
  for (const child of blockEl.children) {
    collectArg(child, out);
  }
}

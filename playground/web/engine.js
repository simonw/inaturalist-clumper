/*
 * Redis array engine, backed by a real WebAssembly compile of antirez's
 * sparsearray.c. Each command implementation here mirrors the semantics
 * documented in src/t_array.c and the per-command JSON specs.
 *
 * The data structure (set/get/del/range-delete, count/len, slice promotion
 * heuristics) lives in WASM. JS owns the keyspace, the per-key insert
 * cursor, and command-level argument parsing/error replies.
 */

import createRedisArrayWasm from "./redis_array.mjs";

const NONE = -1n;            // matches AR_INSERT_IDX_NONE in t_array.c
const U64_MAX = (1n << 64n) - 1n;
const ARGETRANGE_MAX_ITEMS = 1000000n;
const AROP_MATCH_KEYWORDS = new Set(["MATCH"]);

let mod = null;

export async function initEngine() {
  mod = await createRedisArrayWasm();
  return mod;
}

/* ---------- keyspace ---------- */

class ArrayKey {
  constructor() {
    this.ptr = mod._ar_new();
    this.insert_idx = NONE;
  }
  free() { mod._ar_free(this.ptr); this.ptr = 0; }
  count() { return mod._ar_count(this.ptr); }
  len()   { return mod._ar_len(this.ptr); }
  has(idx) { return !!mod._ar_has(this.ptr, idx); }
  get(idx) {
    const cap = 4096;
    const buf = mod._malloc(cap);
    try {
      const n = mod._ar_get_into(this.ptr, idx, buf, cap);
      if (n < 0) return null;
      const len = Math.min(n, cap);
      return new TextDecoder().decode(mod.HEAPU8.slice(buf, buf + len));
    } finally {
      mod._free(buf);
    }
  }
  set(idx, str) {
    const bytes = new TextEncoder().encode(str);
    const buf = mod._malloc(bytes.length || 1);
    try {
      mod.HEAPU8.set(bytes, buf);
      const wasEmpty = mod._ar_set_str(this.ptr, idx, buf, bytes.length);
      return !!wasEmpty;
    } finally {
      mod._free(buf);
    }
  }
  del(idx) { return !!mod._ar_del(this.ptr, idx); }
  delRange(lo, hi) { return mod._ar_delete_range(this.ptr, lo, hi); }
}

const db = new Map();   // name -> ArrayKey

export function reset() {
  for (const k of db.values()) k.free();
  db.clear();
}

export function listKeys() {
  return [...db.entries()].map(([name, key]) => ({
    name,
    count: key.count(),
    len: key.len(),
    insert_idx: key.insert_idx,
  }));
}

export function snapshotKey(name, max_show = 50) {
  const key = db.get(name);
  if (!key) return null;
  const len = Number(key.len());
  if (len === 0) return { name, len: 0n, count: 0n, insert_idx: key.insert_idx, items: [] };

  const cap = Math.min(len, max_show);
  const items = [];
  for (let i = 0; i < cap; i++) {
    const idx = BigInt(i);
    if (key.has(idx)) items.push({ idx, value: key.get(idx) });
    else items.push({ idx, value: null });
  }
  return {
    name,
    len: key.len(),
    count: key.count(),
    insert_idx: key.insert_idx,
    items,
    truncated: len > cap,
  };
}

/* ---------- helpers ---------- */

function parseIndex(s, allowMax = false) {
  if (!/^\d+$/.test(s)) return null;
  const v = BigInt(s);
  if (v < 0n) return null;
  if (!allowMax && v === U64_MAX) return null;
  return v;
}

function getOrCreate(name) {
  let k = db.get(name);
  if (!k) { k = new ArrayKey(); db.set(name, k); }
  return k;
}

function maybeDeleteIfEmpty(name, k) {
  if (k.count() === 0n) {
    k.free();
    db.delete(name);
  }
}

function readBound(token, allowSpecials) {
  if (allowSpecials) {
    if (token === "-") return { kind: "start" };
    if (token === "+") return { kind: "end" };
  }
  const v = parseIndex(token);
  if (v === null) return null;
  return { kind: "index", value: v };
}

function resolveBound(b, max_index) {
  if (b.kind === "start") return 0n;
  if (b.kind === "end") return max_index;
  return b.value;
}

/* ---------- predicate matching for ARGREP ---------- */

function asciiLower(b) {
  return (b >= 0x41 && b <= 0x5a) ? (b + 0x20) : b;
}

function bytesEqual(a, b, nocase) {
  if (a.length !== b.length) return false;
  if (!nocase) {
    for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
    return true;
  }
  for (let i = 0; i < a.length; i++) {
    if (asciiLower(a[i]) !== asciiLower(b[i])) return false;
  }
  return true;
}

function bytesContains(hay, needle, nocase) {
  if (needle.length === 0) return true;
  if (needle.length > hay.length) return false;
  for (let i = 0; i <= hay.length - needle.length; i++) {
    if (bytesEqual(hay.subarray(i, i + needle.length), needle, nocase)) return true;
  }
  return false;
}

/*
 * Implements Redis' stringmatchlen() glob (`*`, `?`, `[...]`, `\`).
 * Mirrors the algorithm in util.c. Operates on byte arrays.
 */
function globMatch(pattern, str, nocase) {
  const patBytes = new TextEncoder().encode(pattern);
  return _stringmatchlen(patBytes, 0, patBytes.length, str, 0, str.length, nocase);
}

function _stringmatchlen(p, pi, pl, s, si, sl, nocase) {
  while (pi < pl && sl > 0) {
    const pc = p[pi];
    if (pc === 0x2a /* * */) {
      while (pi + 1 < pl && p[pi + 1] === 0x2a) pi++;
      if (pi === pl - 1) return true;
      for (let k = 0; k <= sl; k++) {
        if (_stringmatchlen(p, pi + 1, pl, s, si + k, sl - k, nocase)) return true;
      }
      return false;
    } else if (pc === 0x3f /* ? */) {
      pi++; si++; sl--;
    } else if (pc === 0x5b /* [ */) {
      pi++;
      let neg = false;
      if (pi < pl && p[pi] === 0x5e /* ^ */) { neg = true; pi++; }
      let match = false;
      while (pi < pl) {
        if (p[pi] === 0x5c /* \ */ && pi + 1 < pl) {
          pi++;
          if (eqByte(p[pi], s[si], nocase)) match = true;
          pi++;
        } else if (p[pi] === 0x5d /* ] */) {
          pi++; break;
        } else if (pi + 2 < pl && p[pi + 1] === 0x2d /* - */) {
          let lo = p[pi], hi = p[pi + 2];
          if (lo > hi) [lo, hi] = [hi, lo];
          let c = s[si];
          if (nocase) { c = asciiLower(c); lo = asciiLower(lo); hi = asciiLower(hi); }
          if (c >= lo && c <= hi) match = true;
          pi += 3;
        } else {
          if (eqByte(p[pi], s[si], nocase)) match = true;
          pi++;
        }
      }
      if (neg) match = !match;
      if (!match) return false;
      si++; sl--;
    } else if (pc === 0x5c /* \ */ && pi + 1 < pl) {
      pi++;
      if (!eqByte(p[pi], s[si], nocase)) return false;
      pi++; si++; sl--;
    } else {
      if (!eqByte(pc, s[si], nocase)) return false;
      pi++; si++; sl--;
    }
  }
  while (pi < pl && p[pi] === 0x2a) pi++;
  return pi === pl && sl === 0;
}

function eqByte(a, b, nocase) {
  return nocase ? asciiLower(a) === asciiLower(b) : a === b;
}

/* ---------- iterator ---------- */

function* scanRange(key, start, end) {
  // Return (idx, value) pairs in the requested order.
  const asc = start <= end;
  const lo = asc ? start : end;
  const hi = asc ? end : start;
  const max = key.len() === 0n ? -1n : key.len() - 1n;
  if (max < 0n) return;
  const realLo = lo;
  const realHi = hi > max ? max : hi;
  if (realLo > realHi) return;

  if (asc) {
    for (let i = realLo; i <= realHi; i++) {
      if (key.has(i)) yield [i, key.get(i)];
    }
  } else {
    for (let i = realHi; i >= realLo; i--) {
      if (key.has(i)) yield [i, key.get(i)];
      if (i === 0n) break;
    }
  }
}

/* ---------- command dispatch ---------- */

const COMMANDS = {};

function err(msg) { return { type: "error", value: msg }; }
function int(n)   { return { type: "integer", value: BigInt(n) }; }
function bulk(s)  { return { type: "bulk", value: s }; }
function nil()    { return { type: "nil" }; }
function arr(items) { return { type: "array", value: items }; }
function map(pairs) { return { type: "map", value: pairs }; }

COMMANDS.ARGET = (args) => {
  if (args.length !== 2) return err("wrong number of arguments");
  const idx = parseIndex(args[1]);
  if (idx === null) return err("invalid array index");
  const k = db.get(args[0]);
  if (!k) return nil();
  return k.has(idx) ? bulk(k.get(idx)) : nil();
};

COMMANDS.ARMGET = (args) => {
  if (args.length < 2) return err("wrong number of arguments");
  const idxs = [];
  for (let i = 1; i < args.length; i++) {
    const idx = parseIndex(args[i]);
    if (idx === null) return err("invalid array index");
    idxs.push(idx);
  }
  const k = db.get(args[0]);
  return arr(idxs.map(i => (k && k.has(i)) ? bulk(k.get(i)) : nil()));
};

COMMANDS.ARSET = (args) => {
  if (args.length < 3) return err("wrong number of arguments");
  const start = parseIndex(args[1]);
  if (start === null) return err("invalid array index");
  const numValues = args.length - 2;
  const last = start + BigInt(numValues) - 1n;
  if (last < start || last === U64_MAX) return err("array index overflow");

  const k = getOrCreate(args[0]);
  const oldCount = k.count();
  for (let i = 0; i < numValues; i++) {
    k.set(start + BigInt(i), args[2 + i]);
  }
  return int(k.count() - oldCount);
};

COMMANDS.ARMSET = (args) => {
  if (args.length < 3 || (args.length - 1) % 2 !== 0)
    return err("wrong number of arguments");
  const pairs = [];
  for (let i = 1; i < args.length; i += 2) {
    const idx = parseIndex(args[i]);
    if (idx === null) return err("invalid array index");
    pairs.push([idx, args[i + 1]]);
  }
  const k = getOrCreate(args[0]);
  const oldCount = k.count();
  for (const [idx, v] of pairs) k.set(idx, v);
  return int(k.count() - oldCount);
};

COMMANDS.ARDEL = (args) => {
  if (args.length < 2) return err("wrong number of arguments");
  const idxs = [];
  for (let i = 1; i < args.length; i++) {
    const idx = parseIndex(args[i]);
    if (idx === null) return err("invalid array index");
    idxs.push(idx);
  }
  const k = db.get(args[0]);
  if (!k) return int(0);
  let n = 0;
  for (const idx of idxs) if (k.del(idx)) n++;
  maybeDeleteIfEmpty(args[0], k);
  return int(n);
};

COMMANDS.ARDELRANGE = (args) => {
  if (args.length < 3 || (args.length - 1) % 2 !== 0)
    return err("wrong number of arguments");
  const ranges = [];
  for (let i = 1; i < args.length; i += 2) {
    const a = parseIndex(args[i]);
    const b = parseIndex(args[i + 1]);
    if (a === null || b === null) return err("invalid array index");
    ranges.push([a, b]);
  }
  const k = db.get(args[0]);
  if (!k) return int(0);
  let total = 0n;
  for (const [a, b] of ranges) {
    const lo = a <= b ? a : b;
    const hi = a <= b ? b : a;
    total += k.delRange(lo, hi);
  }
  maybeDeleteIfEmpty(args[0], k);
  return int(total);
};

COMMANDS.ARLEN = (args) => {
  if (args.length !== 1) return err("wrong number of arguments");
  const k = db.get(args[0]);
  return int(k ? k.len() : 0n);
};

COMMANDS.ARCOUNT = (args) => {
  if (args.length !== 1) return err("wrong number of arguments");
  const k = db.get(args[0]);
  return int(k ? k.count() : 0n);
};

COMMANDS.ARGETRANGE = (args) => {
  if (args.length !== 3) return err("wrong number of arguments");
  const start = parseIndex(args[1]);
  const end = parseIndex(args[2]);
  if (start === null || end === null) return err("invalid array index");
  const reverse = start > end;
  const lo = reverse ? end : start;
  const hi = reverse ? start : end;
  const len = hi - lo + 1n;
  if (len > ARGETRANGE_MAX_ITEMS)
    return err(`range exceeds maximum of ${ARGETRANGE_MAX_ITEMS} items`);

  const k = db.get(args[0]);
  const out = [];
  if (reverse) {
    for (let i = hi; ; i--) {
      out.push((k && k.has(i)) ? bulk(k.get(i)) : nil());
      if (i === lo) break;
    }
  } else {
    for (let i = lo; i <= hi; i++) {
      out.push((k && k.has(i)) ? bulk(k.get(i)) : nil());
    }
  }
  return arr(out);
};

COMMANDS.ARSCAN = (args) => {
  if (args.length !== 3 && args.length !== 5)
    return err("wrong number of arguments");
  const start = parseIndex(args[1]);
  const end = parseIndex(args[2]);
  if (start === null || end === null) return err("invalid array index");

  let limit = null;
  if (args.length === 5) {
    if (args[3].toUpperCase() !== "LIMIT") return err("syntax error");
    const n = Number(args[4]);
    if (!Number.isFinite(n) || n <= 0 || !/^[+-]?\d+$/.test(args[4]))
      return err("LIMIT must be positive");
    limit = BigInt(args[4]);
  }
  const k = db.get(args[0]);
  if (!k) return arr([]);
  const out = [];
  let remaining = limit ?? -1n;
  for (const [idx, v] of scanRange(k, start, end)) {
    if (remaining === 0n) break;
    out.push(int(idx), bulk(v));
    if (remaining > 0n) remaining--;
  }
  return arr(out);
};

/* ARGREP — search predicates with optional combinators */
COMMANDS.ARGREP = (args) => {
  if (args.length < 5) return err("wrong number of arguments");
  const startBound = readBound(args[1], true);
  const endBound = readBound(args[2], true);
  if (!startBound || !endBound) return err("invalid array index");

  const preds = [];
  let combine = "OR";
  let limit = -1n;
  let withvalues = false;
  let nocase = false;

  let i = 3;
  while (i < args.length) {
    const tok = args[i].toUpperCase();
    if (tok === "EXACT" || tok === "MATCH" || tok === "GLOB" || tok === "RE") {
      if (i + 1 >= args.length) return err("syntax error");
      preds.push({ type: tok, pattern: args[i + 1] });
      i += 2;
    } else if (tok === "LIMIT") {
      if (i + 1 >= args.length) return err("syntax error");
      const n = Number(args[i + 1]);
      if (!Number.isFinite(n) || n <= 0) return err("LIMIT must be positive");
      limit = BigInt(args[i + 1]);
      i += 2;
    } else if (tok === "WITHVALUES") { withvalues = true; i++; }
    else if (tok === "NOCASE") { nocase = true; i++; }
    else if (tok === "AND") { combine = "AND"; i++; }
    else if (tok === "OR") { combine = "OR"; i++; }
    else return err("syntax error");
  }
  if (preds.length === 0) return err("syntax error");

  // Compile RE patterns
  const compiled = preds.map(p => {
    if (p.type === "RE") {
      try {
        return { ...p, regex: new RegExp(p.pattern, nocase ? "i" : "") };
      } catch (e) {
        return { ...p, regex_error: String(e.message) };
      }
    }
    return p;
  });
  for (const p of compiled) {
    if (p.regex_error) return err(`invalid regular expression: ${p.regex_error}`);
  }

  const k = db.get(args[0]);
  if (!k) return arr([]);
  const max = k.len() === 0n ? 0n : k.len() - 1n;
  const start = resolveBound(startBound, max);
  const end = resolveBound(endBound, max);

  const matches = [];
  let remaining = limit;
  for (const [idx, v] of scanRange(k, start, end)) {
    if (remaining === 0n) break;
    const bytes = new TextEncoder().encode(v);
    let ok;
    if (combine === "AND") {
      ok = compiled.every(p => evalPredicate(p, bytes, v, nocase));
    } else {
      ok = compiled.some(p => evalPredicate(p, bytes, v, nocase));
    }
    if (ok) {
      matches.push(int(idx));
      if (withvalues) matches.push(bulk(v));
      if (remaining > 0n) remaining--;
    }
  }
  return arr(matches);
};

function evalPredicate(p, bytes, str, nocase) {
  const needleBytes = new TextEncoder().encode(p.pattern);
  switch (p.type) {
    case "EXACT": return bytesEqual(bytes, needleBytes, nocase);
    case "MATCH": return bytesContains(bytes, needleBytes, nocase);
    case "GLOB":  return globMatch(p.pattern, bytes, nocase);
    case "RE":    return p.regex.test(str);
  }
  return false;
}

/* AROP — aggregate ops */
COMMANDS.AROP = (args) => {
  if (args.length < 4) return err("wrong number of arguments");
  const start = parseIndex(args[1]);
  const end = parseIndex(args[2]);
  if (start === null || end === null) return err("invalid array index");

  const op = args[3].toUpperCase();
  const VALID = ["SUM","MIN","MAX","AND","OR","XOR","MATCH","USED"];
  if (!VALID.includes(op)) return err("unknown operation");

  let matchVal = null;
  if (op === "MATCH") {
    if (args.length !== 5) return err("MATCH requires a value argument");
    matchVal = args[4];
  } else if (args.length !== 4) return err("wrong number of arguments");

  const k = db.get(args[0]);
  if (!k) {
    if (op === "MATCH" || op === "USED") return int(0);
    return nil();
  }

  let sum = 0, min = Infinity, max = -Infinity, andAcc, orAcc = 0n, xorAcc = 0n;
  let hasNumeric = false, hasInt = false;
  let matchCount = 0n, usedCount = 0n;

  for (const [, v] of scanRange(k, start, end)) {
    usedCount++;
    if (op === "MATCH") {
      if (v === matchVal) matchCount++;
      continue;
    }
    if (op === "USED") continue;

    const asInt = /^-?\d+$/.test(v) ? BigInt(v) : null;
    const asNum = Number(v);
    const numericOk = Number.isFinite(asNum) && /^-?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/.test(v);

    if (op === "AND" || op === "OR" || op === "XOR") {
      if (asInt === null) continue;
      if (!hasInt) { andAcc = asInt; orAcc = 0n; xorAcc = 0n; hasInt = true; }
      else if (op === "AND") andAcc &= asInt;
      if (op === "OR") orAcc |= asInt;
      else if (op === "XOR") xorAcc ^= asInt;
      else if (op === "AND" && hasInt) andAcc &= asInt;
      continue;
    }
    if (numericOk) {
      hasNumeric = true;
      if (op === "SUM") sum += asNum;
      else if (op === "MIN") { if (asNum < min) min = asNum; }
      else if (op === "MAX") { if (asNum > max) max = asNum; }
    }
  }

  if (op === "MATCH") return int(matchCount);
  if (op === "USED") return int(usedCount);
  if (op === "AND") return hasInt ? int(andAcc) : nil();
  if (op === "OR")  return hasInt ? int(orAcc) : nil();
  if (op === "XOR") return hasInt ? int(xorAcc) : nil();
  if (!hasNumeric) return nil();
  const result = op === "SUM" ? sum : (op === "MIN" ? min : max);
  return bulk(formatNumber(result));
};

function formatNumber(n) {
  if (Number.isInteger(n)) return String(n);
  return String(n);
}

/* ARINSERT — append at the cursor */
COMMANDS.ARINSERT = (args) => {
  if (args.length < 2) return err("wrong number of arguments");
  const k = getOrCreate(args[0]);
  const numValues = args.length - 1;
  const startCursor = k.insert_idx === NONE ? 0n : k.insert_idx + 1n;
  if (k.insert_idx >= U64_MAX - 1n && k.insert_idx !== NONE)
    return err("insert index overflow");
  const last = startCursor + BigInt(numValues) - 1n;
  if (last < startCursor || last === U64_MAX) return err("insert index overflow");

  let cursor = startCursor;
  for (let i = 0; i < numValues; i++) {
    k.set(cursor, args[1 + i]);
    cursor++;
  }
  k.insert_idx = last;
  return int(k.insert_idx);
};

/* ARRING — ring-buffer insert */
COMMANDS.ARRING = (args) => {
  if (args.length < 3) return err("wrong number of arguments");
  if (!/^-?\d+$/.test(args[1])) return err("invalid size");
  const ll = BigInt(args[1]);
  if (ll <= 0n) return err("size must be positive");
  const ringSize = ll;

  const k = getOrCreate(args[0]);

  // Decide if we need to rework the ring (shrink, or grow after wrap).
  const oldSpan = k.len();
  let needsRework = false;
  let keepSpan = 0n;

  if (oldSpan > 0n) {
    if (ringSize < oldSpan) { needsRework = true; keepSpan = ringSize; }
    else if (ringSize === oldSpan) { /* no-op */ }
    else if (k.insert_idx !== NONE) {
      const nextCursor = k.insert_idx + 1n;
      if (nextCursor < oldSpan) { needsRework = true; keepSpan = oldSpan; }
    }
  }

  if (needsRework) {
    const anchor = k.insert_idx === NONE ? oldSpan - 1n : (k.insert_idx % oldSpan);
    const retained = [];
    let src = anchor;
    while (BigInt(retained.length) < keepSpan) {
      if (!k.has(src)) break;
      retained.push(k.get(src));
      if (src === 0n) src = oldSpan - 1n; else src--;
    }
    retained.reverse();
    // rebuild
    const newKey = new ArrayKey();
    for (let i = 0; i < retained.length; i++) newKey.set(BigInt(i), retained[i]);
    if (retained.length > 0) newKey.insert_idx = BigInt(retained.length - 1);
    k.free();
    db.set(args[0], newKey);
    // continue with new key
    return _arringInsert(args[0], ringSize, args.slice(2));
  }

  return _arringInsert(args[0], ringSize, args.slice(2));
};

function _arringInsert(name, ringSize, values) {
  const k = db.get(name);
  let cursor = 0n;
  for (const v of values) {
    cursor = k.insert_idx === NONE ? 0n : k.insert_idx + 1n;
    if (cursor >= ringSize) cursor = cursor % ringSize;
    k.set(cursor, v);
    k.insert_idx = cursor;
  }
  return int(cursor);
}

COMMANDS.ARNEXT = (args) => {
  if (args.length !== 1) return err("wrong number of arguments");
  const k = db.get(args[0]);
  if (!k) return int(0);
  if (k.insert_idx === NONE) return int(0);
  if (k.insert_idx === U64_MAX - 1n) return nil();
  return int(k.insert_idx + 1n);
};

COMMANDS.ARSEEK = (args) => {
  if (args.length !== 2) return err("wrong number of arguments");
  const idx = parseIndex(args[1], true);
  if (idx === null) return err("invalid array index");
  const k = db.get(args[0]);
  if (!k) return int(0);
  if (idx === 0n) k.insert_idx = NONE;
  else k.insert_idx = idx - 1n;
  return int(1);
};

COMMANDS.ARLASTITEMS = (args) => {
  if (args.length !== 2 && args.length !== 3) return err("wrong number of arguments");
  if (!/^-?\d+$/.test(args[1])) return err("invalid COUNT");
  const count = BigInt(args[1]);
  if (count <= 0n) return arr([]);
  let rev = false;
  if (args.length === 3) {
    if (args[2].toUpperCase() !== "REV") return err("syntax error");
    rev = true;
  }
  const k = db.get(args[0]);
  if (!k) return arr([]);
  const arLen = k.len();
  if (arLen === 0n) return arr([]);
  const effective = count > k.count() ? k.count() : count;
  if (effective === 0n) return arr([]);

  const collected = [];
  const anchor = k.insert_idx === NONE ? arLen - 1n : k.insert_idx;
  let cur = anchor;
  while (BigInt(collected.length) < effective) {
    collected.push(k.has(cur) ? bulk(k.get(cur)) : nil());
    if (cur === 0n) cur = arLen - 1n;
    else cur--;
  }
  return arr(rev ? collected : collected.reverse());
};

COMMANDS.ARINFO = (args) => {
  if (args.length !== 1 && args.length !== 2) return err("wrong number of arguments");
  let full = false;
  if (args.length === 2) {
    if (args[1].toUpperCase() !== "FULL") return err("syntax error");
    full = true;
  }
  const k = db.get(args[0]);
  if (!k) return err("no such key");
  let nextIdx;
  if (k.insert_idx === NONE || k.insert_idx === U64_MAX - 1n) nextIdx = 0n;
  else nextIdx = k.insert_idx + 1n;

  const pairs = [
    ["count", int(k.count())],
    ["len", int(k.len())],
    ["next-insert-index", int(nextIdx)],
    ["slices", int(0n)],          // not exposed via WASM API
    ["directory-size", int(0n)],
    ["super-dir-entries", int(0n)],
    ["slice-size", int(4096n)],
  ];
  if (full) {
    pairs.push(
      ["dense-slices", int(0n)],
      ["sparse-slices", int(0n)],
      ["avg-dense-size", bulk("0")],
      ["avg-dense-fill", bulk("0")],
      ["avg-sparse-size", bulk("0")],
    );
  }
  return map(pairs);
};

/* ---------- public dispatch ---------- */

export function execute(name, args) {
  const fn = COMMANDS[name];
  if (!fn) return err(`unknown command '${name}'`);
  try {
    return fn(args);
  } catch (e) {
    return err(`engine error: ${e.message}`);
  }
}

export function commandNames() { return Object.keys(COMMANDS); }

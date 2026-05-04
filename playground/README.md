# Redis Array Playground

A static, browser-only playground for the new `AR*` array commands proposed
in [redis/redis#15162](https://github.com/redis/redis/pull/15162) and described
in [antirez's blog post](https://antirez.com/news/164).

## What's in here

```
playground/
├── build_commands_json.py   # combines src/commands/ar*.json -> commands.json
├── wasm-src/                # standalone WASM build of sparsearray.c
│   ├── sparsearray.c        # copied from antirez:array branch
│   ├── sparsearray.h        # copied from antirez:array branch
│   ├── server.h             # minimal stubs (zmalloc, serverAssert, ...)
│   ├── util_shim.c          # string2ll, d2string, ll2string shims
│   └── wasm_main.c          # ar_new/ar_set_str/ar_get_into/... JS bridge
└── web/                     # the playground itself (static files)
    ├── index.html
    ├── styles.css
    ├── main.js              # UI controller
    ├── ui.js                # dynamic form generator
    ├── engine.js            # command-level logic on top of WASM
    ├── commands.json        # generated from src/commands/ar*.json
    ├── redis_array.mjs      # emscripten loader
    └── redis_array.wasm     # antirez's sparse-array data structure, in WASM
```

## How it's wired

1. `build_commands_json.py` reads every `src/commands/ar*.json` file from a
   Redis source tree and writes them into one combined `commands.json`.
2. The browser fetches that JSON and uses each spec to render a form (key,
   integer, string, repeating values, oneof choosers, nested blocks).
3. The browser also loads `redis_array.wasm` — a real WebAssembly compile of
   `sparsearray.c` from the antirez:array branch. That module owns the
   storage: tagged pointer encoding, sparse and dense slices, slice promotion,
   ranged delete, etc.
4. `engine.js` parses each command's arguments, applies validation, and
   forwards storage operations to WASM. The per-key `insert_idx` cursor used
   by `ARINSERT` / `ARRING` / `ARSEEK` lives JS-side.

## Why not full Redis-to-WASM?

A full port of Redis 8.x to WASM is a real effort: `fork()` for snapshotting,
POSIX networking, signal handling, threads, jemalloc, Lua, hiredis,
hdr_histogram, the cluster code, the module API. None of that is needed to
demo the `AR*` commands, so this playground compiles only the new sparse-array
data structure and runs the command dispatcher in JS — keeping the most
interesting code (antirez's tagged-pointer sparse array) running as actual
WebAssembly.

## Build

The committed `web/redis_array.wasm` is already built. To rebuild:

```bash
# 1) Get emscripten (if you don't have it)
git clone https://github.com/emscripten-core/emsdk.git /tmp/emsdk
/tmp/emsdk/emsdk install latest
/tmp/emsdk/emsdk activate latest
source /tmp/emsdk/emsdk_env.sh

# 2) Get antirez:array
git clone https://github.com/redis/redis.git /tmp/redis
cd /tmp/redis
git remote add antirez https://github.com/antirez/redis.git
git fetch antirez array
git checkout antirez/array -b array

# 3) Refresh the WASM
cp /tmp/redis/src/sparsearray.{c,h} playground/wasm-src/
cd playground/wasm-src
emcc -O2 -I. sparsearray.c util_shim.c wasm_main.c \
  -s EXPORTED_FUNCTIONS="['_ar_new','_ar_free','_ar_count','_ar_len','_ar_set_str','_ar_del','_ar_delete_range','_ar_get_into','_ar_has','_malloc','_free']" \
  -s EXPORTED_RUNTIME_METHODS="['HEAPU8','HEAP8']" \
  -s ALLOW_MEMORY_GROWTH=1 -s MODULARIZE=1 -s EXPORT_ES6=1 \
  -s ENVIRONMENT=web,worker -s EXPORT_NAME=createRedisArrayWasm \
  -s WASM_BIGINT=1 -o ../web/redis_array.mjs
cp redis_array.wasm ../web/

# 4) Refresh the combined command JSON
cd ../..
python3 playground/build_commands_json.py /tmp/redis/src/commands playground/web/commands.json
```

## Run

It's a static site:

```bash
cd playground/web
python3 -m http.server 8765
# open http://localhost:8765/
```

Some browsers block ES module fetches over `file://`, so a local HTTP server
is recommended.

/*
 * Thin wrapper to expose sparse-array operations to JavaScript.
 *
 * Only the underlying data structure (sparsearray.c, written by antirez for
 * the array branch) is compiled to WebAssembly. Command parsing, replies, and
 * key/db management run in JavaScript.
 */
#include "server.h"
#include "sparsearray.h"
#include <emscripten.h>
#include <math.h>

struct serverConfig server = {
    .array_slice_size = 4096,
    .array_sparse_kmax = 10,
    .array_sparse_kmin = 5,
};

EMSCRIPTEN_KEEPALIVE
redisArray *ar_new(void) { return arNew(); }

EMSCRIPTEN_KEEPALIVE
void ar_free(redisArray *ar) { arFree(ar); }

EMSCRIPTEN_KEEPALIVE
uint64_t ar_count(redisArray *ar) { return arCount(ar); }

EMSCRIPTEN_KEEPALIVE
uint64_t ar_len(redisArray *ar) { return arLen(ar); }

/* Set a string value at idx. Returns 1 if the slot was previously empty. */
EMSCRIPTEN_KEEPALIVE
int ar_set_str(redisArray *ar, uint64_t idx, const char *s, int len) {
    int was_empty = (arGet(ar, idx) == NULL) ? 1 : 0;
    arSet(ar, idx, arEncode(s, (size_t)len));
    return was_empty;
}

EMSCRIPTEN_KEEPALIVE
int ar_del(redisArray *ar, uint64_t idx) { return arDel(ar, idx); }

EMSCRIPTEN_KEEPALIVE
uint64_t ar_delete_range(redisArray *ar, uint64_t lo, uint64_t hi) {
    return arDeleteRange(ar, lo, hi);
}

/* Read a value into a caller-provided buffer.
 * Returns the length, or -1 if the slot is empty. The buffer must be large
 * enough; the caller can size it via ar_get_len_hint. */
EMSCRIPTEN_KEEPALIVE
int ar_get_into(redisArray *ar, uint64_t idx, char *out, int max_len) {
    void *v = arGet(ar, idx);
    if (v == NULL) return -1;

    char inline_buf[64];
    size_t outlen = 0;
    const char *data = arDecode(v, inline_buf, sizeof(inline_buf), &outlen);
    int n = (int)outlen;
    if (n > max_len) n = max_len;
    if (n > 0) memcpy(out, data, (size_t)n);
    return (int)outlen;
}

/* Probe-only call: returns 1 if the slot has a value, 0 otherwise. */
EMSCRIPTEN_KEEPALIVE
int ar_has(redisArray *ar, uint64_t idx) {
    return arGet(ar, idx) != NULL ? 1 : 0;
}

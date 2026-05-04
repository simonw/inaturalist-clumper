/*
 * Minimal server.h shim for compiling sparsearray.c standalone to WASM.
 * Only the symbols actually referenced by sparsearray.c are stubbed here.
 */
#ifndef __WASM_SERVER_SHIM_H
#define __WASM_SERVER_SHIM_H

#include <stdlib.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>

#define UNUSED(x) ((void)(x))

static inline void *zmalloc(size_t size) { return malloc(size); }
static inline void *zcalloc(size_t size) { return calloc(1, size); }
static inline void *zrealloc(void *ptr, size_t size) { return realloc(ptr, size); }
static inline void zfree(void *ptr) { free(ptr); }

/* Without a real allocator we don't know how big a block is. Returning the
 * requested size is wrong but, since alloc_size accounting is only used by
 * Redis monitoring, the WASM playground does not depend on its accuracy. */
static inline size_t zmalloc_size(void *ptr) { (void)ptr; return 0; }

#define serverAssert(x) do { if (!(x)) { fprintf(stderr, "assert failed: %s\n", #x); abort(); } } while(0)
#define serverPanic(...) do { fprintf(stderr, __VA_ARGS__); abort(); } while(0)

#include "sparsearray.h"

struct serverConfig {
    size_t array_slice_size;
    size_t array_sparse_kmax;
    size_t array_sparse_kmin;
    /* Defrag-related fields are referenced even though defrag is unused
     * in the WASM playground. */
    unsigned long stat_active_defrag_scanned;
    unsigned long active_defrag_max_scan_fields;
};

extern struct serverConfig server;

/* Forward declarations. Implemented in util_shim.c. */
int string2ll(const char *s, size_t slen, long long *value);
int string2d(const char *s, size_t slen, double *dp);
int d2string(char *buf, size_t len, double value);
int ll2string(char *dst, size_t dstlen, long long svalue);

#endif

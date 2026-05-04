/*
 * Minimal Redis util.c shims required to compile sparsearray.c standalone.
 * Behavior matches Redis well enough for the values used by the WASM
 * playground (printable strings, ASCII ints, finite doubles).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <errno.h>
#include <math.h>

int string2ll(const char *s, size_t slen, long long *value) {
    if (slen == 0) return 0;
    char buf[64];
    if (slen >= sizeof(buf)) return 0;
    memcpy(buf, s, slen);
    buf[slen] = '\0';
    char *end;
    errno = 0;
    long long v = strtoll(buf, &end, 10);
    if (errno || *end != '\0') return 0;
    if (value) *value = v;
    return 1;
}

int string2d(const char *s, size_t slen, double *dp) {
    if (slen == 0) return 0;
    char buf[64];
    if (slen >= sizeof(buf)) return 0;
    memcpy(buf, s, slen);
    buf[slen] = '\0';
    char *end;
    errno = 0;
    double v = strtod(buf, &end);
    if (errno || *end != '\0') return 0;
    if (!isfinite(v)) return 0;
    if (dp) *dp = v;
    return 1;
}

int d2string(char *buf, size_t len, double value) {
    if (isnan(value)) return snprintf(buf, len, "nan");
    if (!isfinite(value)) return snprintf(buf, len, value > 0 ? "inf" : "-inf");
    if (value == (long long)value)
        return snprintf(buf, len, "%lld", (long long)value);
    int n = snprintf(buf, len, "%.17g", value);
    return n;
}

int ll2string(char *dst, size_t dstlen, long long svalue) {
    return snprintf(dst, dstlen, "%lld", svalue);
}

#ifdef BENCH_COUNT
static uint64_t bench_tags, bench_ops, bench_loads, bench_stores, bench_fallbacks, bench_opens;
#define BENCH_COUNT_ONE(key) (++bench_##key)
static void bench_report_counts(void) {
    fprintf(stderr, "cost counters: tags=%llu ops=%llu loads=%llu stores=%llu fallback=%llu views=%llu\n",
            (unsigned long long)bench_tags, (unsigned long long)bench_ops,
            (unsigned long long)bench_loads, (unsigned long long)bench_stores,
            (unsigned long long)bench_fallbacks, (unsigned long long)bench_opens);
}
#else
#define BENCH_COUNT_ONE(key) ((void)0)
#endif

/* Used only in tagged paths of the byte-for-byte matched numeric decoder.
 * The register experiment changes the access API, preserving each slot read
 * and write. In-range numeric slots use the native storage. */
static inline sp_oint bench_reg_read(sp_IntArray *r, sp_int i) {
    if ((uint64_t)i < (uint64_t)r->len && !r->nilbits)
        return sp_oint_of(r->data[r->start + i]);
    return sp_IntArray_oget(r, i);
}
static inline sp_oint bench_reg_fetch(sp_IntArray *r, sp_int i) {
    if ((uint64_t)i >= (uint64_t)r->len)
        sp_raise_cls("IndexError", "unexpected register in the matched MIR");
    /* Spinel's generated fetch calls get, returning an integer. */
    return sp_oint_of(r->data[r->start + i]);
}
static inline void bench_reg_write(sp_IntArray *r, sp_int i, sp_int v) {
    if (!r->frozen && !r->nilbits && (uint64_t)i < (uint64_t)r->len)
        r->data[r->start + i] = v;
    else
        sp_IntArray_set(r, i, v);
}
static inline void bench_reg_copy(sp_IntArray *r, sp_int i, sp_oint v) {
    if (v.nil) sp_IntArray_set_nil(r, i);
    else bench_reg_write(r, i, v.v);
}

/* A run of matched MIR operations has no call or memory.grow. Any return
 * to a non-experimental opcode invalidates this view. Keep the Wasm bounds
 * check per access and take the original path on errors or invalid views. */
typedef struct { uint8_t *data; sp_int len, writable; } bench_view_t;

static inline void bench_open_view(bench_view_t *v, sp_StoreAccess *s) {
    sp_IOBuffer *b = sp_Memory_buffer(sp_StoreAccess_memory(s));
    v->data = sp_iob_view(b, &v->len);
    v->writable = sp_iob_view_wlen(b, v->len);
    BENCH_COUNT_ONE(opens);
}

static inline sp_int bench_load(bench_view_t *v, sp_StoreAccess *s,
                                sp_oint address, sp_oint offset) {
    if (!v->data) bench_open_view(v, s);
    sp_int pos = sp_int_add(sp_oint_arg(address), sp_oint_arg(offset));
    if (v->data && (uint64_t)pos < (uint64_t)v->len) {
        BENCH_COUNT_ONE(loads);
        return v->data[pos];
    }
    BENCH_COUNT_ONE(fallbacks);
    return sp_StoreAccess_load8_u(s, address, offset);
}

static inline void bench_store(bench_view_t *v, sp_StoreAccess *s,
                               sp_oint address, sp_oint offset, sp_int width, sp_oint value) {
    if (!v->data) bench_open_view(v, s);
    sp_int pos = sp_int_add(sp_oint_arg(address), sp_oint_arg(offset));
    if (v->data && !value.nil && (width == 2 || width == 4) &&
        (uint64_t)pos < (uint64_t)v->writable && (uint64_t)width <= (uint64_t)v->writable - (uint64_t)pos) {
        BENCH_COUNT_ONE(stores);
        sp_iob_store(v->data + pos, width, 0, (uint64_t)value.v);
        return;
    }
    BENCH_COUNT_ONE(fallbacks);
    sp_StoreAccess_store(s, address, offset, width, value);
}

static inline sp_oint bench_operand(sp_IntArray *words, sp_int i) {
    if ((uint64_t)i >= (uint64_t)words->len)
        sp_raise_cls("IndexError", "invalid operand in the matched MIR");
    return sp_oint_of(words->data[words->start + i]);
}

/* Retain all 64 bits of the WebAssembly result in Spinel's carrier. */
static inline sp_int bench_shl(sp_int value, sp_int count) {
    return (sp_int)((uint64_t)value << ((uint64_t)count & 63));
}
static inline sp_int bench_shr(sp_int value, sp_int count) {
    return (sp_int)((uint64_t)value >> ((uint64_t)count & 63));
}

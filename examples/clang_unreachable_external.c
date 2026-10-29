/* The calls backend must prove the entire external call unreachable.
 * No return, side-effect or noreturn behavior is assumed for opaque_sink.
 * x in [0, 1000] succeeds; including -1 yields an analysis frontier witness.
 */
extern void opaque_sink(const char *, int, const char *);

int entry(int x) {
  if (x < 0)
    opaque_sink("unmodeled external behavior", x, __func__);
  return x + 1;
}

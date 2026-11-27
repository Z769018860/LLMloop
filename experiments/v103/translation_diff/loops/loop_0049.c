int f(int p0) {
  int i = 0;
  int s = 1;
  int t0 = p0;
  int t1 = p0;
  while (i < p0 + 2) { i = i + 2; s = s + p0 * 2; t0 = t0 + p0 * 2; t1 = t1 + 2; }
  return t0;
}

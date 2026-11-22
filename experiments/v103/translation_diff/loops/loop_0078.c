int f(int p0, int p1) {
  int i = 0;
  int s = p1;
  int t0 = p0;
  int t1 = 0;
  while (i < 8) { i = i + 1; s = s + p0 * 2; t0 = t0 + 2; t1 = t1 + 2; }
  return t1;
}

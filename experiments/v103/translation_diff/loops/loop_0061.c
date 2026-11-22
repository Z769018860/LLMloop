int f(int p0, int p1) {
  int i = 0;
  int s = 0;
  int t0 = p1;
  int t1 = 2;
  while (i < 4 + p1) { i = i + 1; s = s + p0 * 2; t0 = t0 + p0 * 2; t1 = t1 + 2; }
  return t0;
}

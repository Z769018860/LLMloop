int f(int p0, int p1, int p2) {
  int i = 0;
  int s = p0;
  int t0 = p0;
  while (i < 10) { i = i + 1; s = s + 2; t0 = t0 + p0 * 2; }
  return i;
}

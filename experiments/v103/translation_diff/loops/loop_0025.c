int f(int p0, int p1, int p2) {
  int i = 0;
  int s = 0;
  int t0 = 0;
  while (i < 8) { i = i + 2; s = s + 3; t0 = t0 + p0 * 2; }
  return t0;
}

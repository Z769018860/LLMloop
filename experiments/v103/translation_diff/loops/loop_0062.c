int f(int p0, int p1) {
  int i = 0;
  int s = p0;
  int t0 = 2;
  int t1 = p0;
  while (i < 4 + p1) { i = i + 3; s = s + p0 * 2; t0 = t0 + 2; t1 = t1 + 1; }
  return t0;
}

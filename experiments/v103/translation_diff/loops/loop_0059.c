int f(int p0, int p1, int p2) {
  int i = 0;
  int s = 1;
  int t0 = 2;
  int t1 = p1;
  while (i < p0 + 2) { i = i + 2; s = s + 1; t0 = t0 + p0 * 2; t1 = t1 + 2; }
  return s;
}

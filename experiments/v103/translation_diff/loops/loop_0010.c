int f(int p0, int p1, int p2) {
  int i = 0;
  int s = 1;
  int t0 = p2;
  int t1 = p0;
  while (i < 10) { i = i + 3; s = s + 1 + p2; t0 = t0 + 2; t1 = t1 + p0 * 2; }
  return s;
}

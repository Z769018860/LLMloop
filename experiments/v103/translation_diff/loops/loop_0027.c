int f(int p0, int p1) {
  int i = 0;
  int s = p0;
  int t0 = 2;
  int t1 = p1;
  while (i < p1) { i = i + 3; s = s + 2; t0 = t0 + 1 + p1; t1 = t1 + p0 * 2; }
  return t0;
}

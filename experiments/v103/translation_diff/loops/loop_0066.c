int f(int p0, int p1, int p2) {
  int i = 0;
  int s = 0;
  int t0 = p1;
  int t1 = p0;
  while (i < p0 + 2) { i = i + 1; s = s + p0 * 2; t0 = t0 + p0; t1 = t1 + 3; }
  return i;
}

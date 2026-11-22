int f(int p0, int p1, int p2) {
  int i = 0;
  int s = p1;
  int t0 = 0;
  int t1 = 2;
  while (i < p2) { i = i + 2; s = s + 3; t0 = t0 + 1 + p2; t1 = t1 + p0 * 2; }
  return i;
}

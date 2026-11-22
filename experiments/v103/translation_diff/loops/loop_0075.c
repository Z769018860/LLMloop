int f(int p0, int p1, int p2) {
  int i = 0;
  int s = p0;
  int t0 = p0;
  int t1 = 0;
  while (i < 6) { i = i + 2; s = s + 1 + p2; t0 = t0 + 1; t1 = t1 + 3; }
  return i;
}

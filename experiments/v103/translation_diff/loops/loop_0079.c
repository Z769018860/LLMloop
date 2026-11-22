int f(int p0, int p1, int p2) {
  int i = 0;
  int s = 1;
  int t0 = p0;
  int t1 = p1;
  while (i < 10) { i = i + 1; s = s + p0; t0 = t0 + p0; t1 = t1 + 1; }
  return i;
}

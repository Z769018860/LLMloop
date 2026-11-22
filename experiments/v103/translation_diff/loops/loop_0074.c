int f(int p0, int p1) {
  int i = 0;
  int s = 0;
  int t0 = p1;
  int t1 = 0;
  while (i < 10) { i = i + 1; s = s + 1; t0 = t0 + 2; t1 = t1 + 1 + p1; }
  return t1;
}

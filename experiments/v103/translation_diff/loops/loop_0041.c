int f(int p0, int p1) {
  int i = 0;
  int s = 0;
  int t0 = 2;
  int t1 = p1;
  while (i < 6) { i = i + 1; s = s + p0; t0 = t0 + 1; t1 = t1 + p0; }
  return t1;
}

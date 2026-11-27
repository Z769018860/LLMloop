int f(int p0, int p1) {
  int i = 0;
  int s = 0;
  int t0 = 0;
  int t1 = 0;
  while (i < p1) { i = i + 2; s = s + p0; t0 = t0 + p0; t1 = t1 + p0; }
  return t1;
}

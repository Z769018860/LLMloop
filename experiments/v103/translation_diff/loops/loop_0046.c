int f(int p0, int p1) {
  int i = 0;
  int s = 1;
  int t0 = p1;
  int t1 = 2;
  while (i < 10) { i = i + 3; s = s + 3; t0 = t0 + p0 * 2; t1 = t1 + p0; }
  return t1;
}

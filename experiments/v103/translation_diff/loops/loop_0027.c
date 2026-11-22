int f(int p0, int p1) {
  int i = 0;
  int s = p1;
  int t0 = p1;
  int t1 = p1;
  while (i < 10) { i = i + 1; s = s + 2; t0 = t0 + p0 * 2; t1 = t1 + p0; }
  return i;
}

int f(int p0) {
  int i = 0;
  int s = 0;
  int t0 = 2;
  int t1 = 2;
  while (i < p0 + 2) { i = i + 2; s = s + 1 + p0; t0 = t0 + 1; t1 = t1 + p0 * 2; }
  return i;
}

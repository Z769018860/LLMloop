int f(int p0, int p1) {
  int i = 0;
  int s = 0;
  int t0 = 0;
  while (i < 8) { i = i + 3; s = s + p0; t0 = t0 + p0 * 2; }
  return s;
}

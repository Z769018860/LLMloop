int f(int p0, int p1) {
  int i = 0;
  int s = p0;
  int t0 = p1;
  while (i < p0 + 2) { i = i + 3; s = s + p0 * 2; t0 = t0 + 2; }
  return i;
}

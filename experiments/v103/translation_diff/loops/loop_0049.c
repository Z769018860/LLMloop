int f(int p0, int p1, int p2) {
  int i = 0;
  int s = p0;
  int t0 = p1;
  while (i < 6) { i = i + 1; s = s + 1; t0 = t0 + 1 + p2; }
  return t0;
}

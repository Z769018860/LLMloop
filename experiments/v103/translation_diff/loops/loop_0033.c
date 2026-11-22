int f(int p0, int p1) {
  int i = 0;
  int s = p0;
  int t0 = p1;
  while (i < 4 + p1) { i = i + 2; s = s + 1 + p1; t0 = t0 + 1 + p1; }
  return t0;
}

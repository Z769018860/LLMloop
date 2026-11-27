int f(int p0, int p1, int p2) {
  int i = 0;
  int s = 0;
  int t0 = 2;
  while (i < p0 + 2) { i = i + 1; s = s + p0; t0 = t0 + 1 + p2; }
  return i;
}

int f(int p0, int p1) {
  int i = 0;
  int s = 1;
  int t0 = p1;
  while (i < 4 + p1) { i = i + 2; s = s + 2; t0 = t0 + 1; }
  return s;
}

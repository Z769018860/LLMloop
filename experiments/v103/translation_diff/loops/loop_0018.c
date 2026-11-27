int f(int p0, int p1) {
  int i = 0;
  int s = 1;
  int t0 = p0;
  while (i < 4 + p1) { i = i + 1; s = s + p0; t0 = t0 + 3; }
  return t0;
}

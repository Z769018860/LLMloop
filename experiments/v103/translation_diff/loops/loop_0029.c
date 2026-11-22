int f(int p0, int p1) {
  int i = 0;
  int s = p1;
  int t0 = p0;
  while (i < p0 + 2) { i = i + 1; s = s + p0; t0 = t0 + 2; }
  return i;
}

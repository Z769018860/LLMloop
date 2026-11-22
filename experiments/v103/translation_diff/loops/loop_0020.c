int f(int p0, int p1) {
  int i = 0;
  int s = 1;
  int t0 = 2;
  while (i < p0 + 2) { i = i + 1; s = s + 1 + p1; t0 = t0 + p0; }
  return i;
}

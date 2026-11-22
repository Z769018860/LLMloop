int f(int p0, int p1) {
  int i = 0;
  int s = p1;
  int t0 = p0;
  int t1 = p0;
  while (i < p0 + 2) { i = i + 2; s = s + 3; t0 = t0 + p0; t1 = t1 + 1 + p1; }
  return i;
}

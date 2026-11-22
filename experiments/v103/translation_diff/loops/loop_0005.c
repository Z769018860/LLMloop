int f(int p0, int p1, int p2) {
  int i = 0;
  int s = 1;
  int t0 = p1;
  int t1 = p0;
  while (i < p2) { i = i + 1; s = s + 3; t0 = t0 + 1; t1 = t1 + 2; }
  return s;
}

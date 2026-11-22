int f(int p0, int p1, int p2) {
  int i = 0;
  int s = p1;
  int t0 = 2;
  int t1 = 2;
  while (i < 4 + p2) { i = i + 3; s = s + 2; t0 = t0 + 2; t1 = t1 + 1 + p2; }
  return s;
}

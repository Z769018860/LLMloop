int f(int p0, int p1, int p2) {
  int i = 0;
  int s = p2;
  int t0 = p2;
  int t1 = p1;
  while (i < 6) { i = i + 2; s = s + 1; t0 = t0 + 1; t1 = t1 + 3; }
  return t1;
}

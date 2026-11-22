int f(int p0, int p1, int p2) {
  int i = 0;
  int s = p1;
  int t0 = p2;
  int t1 = p2;
  while (i < 4 + p2) { i = i + 2; s = s + 1 + p2; t0 = t0 + p0; t1 = t1 + 1 + p2; }
  return i;
}

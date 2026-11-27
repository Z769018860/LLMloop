int f(int p0, int p1) {
  int i = 0;
  int s = 1;
  int t0 = 0;
  int t1 = 2;
  while (i < 4 + p1) { i = i + 3; s = s + 2; t0 = t0 + 1 + p1; t1 = t1 + p0; }
  return t0;
}

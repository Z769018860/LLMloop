int f(int p0) {
  int i = 0;
  int s = 1;
  int t0 = p0;
  int t1 = 2;
  while (i < 10) { i = i + 1; s = s + p0 * 2; t0 = t0 + 3; t1 = t1 + 2; }
  return s;
}

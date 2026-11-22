int f(int p0) {
  int i = 0;
  int s = 1;
  int t0 = p0;
  int t1 = 2;
  while (i < 4 + p0) { i = i + 1; s = s + 3; t0 = t0 + p0 * 2; t1 = t1 + p0 * 2; }
  return i;
}

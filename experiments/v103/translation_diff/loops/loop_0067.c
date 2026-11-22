int f(int p0) {
  int i = 0;
  int s = 0;
  int t0 = 2;
  while (i < 4 + p0) { i = i + 3; s = s + 1 + p0; t0 = t0 + p0 * 2; }
  return s;
}

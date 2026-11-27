int f(int p0) {
  int i = 0;
  int s = 0;
  int t0 = p0;
  while (i < 4 + p0) { i = i + 1; s = s + p0 * 2; t0 = t0 + 3; }
  return i;
}

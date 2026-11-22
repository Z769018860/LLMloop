int f(int p0) {
  int i = 0;
  int s = p0;
  int t0 = p0;
  while (i < 10) { i = i + 2; s = s + 3; t0 = t0 + 1 + p0; }
  return t0;
}

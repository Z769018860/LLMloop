int f(int p0) {
  int i = 0;
  int s = p0;
  int t0 = 0;
  int t1 = 0;
  while (i < 8) { i = i + 1; s = s + 2; t0 = t0 + p0; t1 = t1 + 3; }
  return t0;
}

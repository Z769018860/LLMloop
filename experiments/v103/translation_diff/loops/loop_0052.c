int f(int p0) {
  int i = 0;
  int s = p0;
  int t0 = 0;
  int t1 = p0;
  while (i < p0 + 2) { i = i + 1; s = s + 2; t0 = t0 + p0; t1 = t1 + 2; }
  return t1;
}

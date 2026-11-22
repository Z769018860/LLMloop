int f(int p0) {
  int i = 0;
  int s = 1;
  int t0 = 2;
  int t1 = p0;
  while (i < p0) { i = i + 2; s = s + 1; t0 = t0 + 2; t1 = t1 + p0; }
  return t1;
}

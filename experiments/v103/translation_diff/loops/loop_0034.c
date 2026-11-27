int f(int p0) {
  int i = 0;
  int s = 0;
  int t0 = p0;
  int t1 = 2;
  while (i < 6) { i = i + 1; s = s + 3; t0 = t0 + 3; t1 = t1 + 1 + p0; }
  return i;
}

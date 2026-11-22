int f(int p0) {
  int i = 0;
  int s = 1;
  int t0 = 0;
  int t1 = 2;
  while (i < 8) { i = i + 3; s = s + 3; t0 = t0 + 2; t1 = t1 + 1 + p0; }
  return t1;
}

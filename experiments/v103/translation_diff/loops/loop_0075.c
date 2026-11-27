int f(int p0, int p1, int p2) {
  int i = 0;
  int s = p0;
  int t0 = p1;
  while (i < 4 + p2) { i = i + 3; s = s + p0; t0 = t0 + 3; }
  return i;
}

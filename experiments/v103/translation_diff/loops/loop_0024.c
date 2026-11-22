int f(int p0, int p1) {
  int i = 0;
  int s = p0;
  while (i < p1) { i = i + 1; s = s + 1 + p1; }
  return s;
}

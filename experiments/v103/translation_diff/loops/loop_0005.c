int f(int p0, int p1, int p2) {
  int i = 0;
  int s = p1;
  while (i < 8) { i = i + 1; s = s + 1 + p2; }
  return s;
}

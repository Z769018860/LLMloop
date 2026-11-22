int f(int p0, int p1) {
  int i = 0;
  int s = p1;
  while (i < 4 + p1) { i = i + 2; s = s + 1; }
  return i;
}

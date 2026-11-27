int f(int p0, int p1) {
  int i = 0;
  int s = p1;
  while (i < 4 + p1) { i = i + 3; s = s + 1 + p1; }
  return s;
}

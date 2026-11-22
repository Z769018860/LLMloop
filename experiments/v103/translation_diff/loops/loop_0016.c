int f(int p0, int p1) {
  int i = 0;
  int s = 0;
  while (i < 4 + p1) { i = i + 3; s = s + p0; }
  return i;
}

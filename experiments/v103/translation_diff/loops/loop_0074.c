int f(int p0, int p1) {
  int i = 0;
  int s = p1;
  while (i < 6) { i = i + 3; s = s + p0; }
  return s;
}

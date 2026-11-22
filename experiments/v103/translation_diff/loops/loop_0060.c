int f(int p0) {
  int i = 0;
  int s = 0;
  while (i < 4 + p0) { i = i + 3; s = s + p0 * 2; }
  return s;
}

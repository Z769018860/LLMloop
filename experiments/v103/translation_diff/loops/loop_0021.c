int f(int p0) {
  int i = 0;
  int s = 1;
  while (i < 6) { i = i + 2; s = s + p0 * 2; }
  return i;
}

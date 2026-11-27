int f(int p0, int p1) {
  int i = 0;
  int s = 1;
  while (i < p1) { i = i + 1; s = s + p0; }
  return i;
}

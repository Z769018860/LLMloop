int f(int p0) {
  int i = 0;
  int s = p0;
  while (i < 10) { i = i + 1; s = s + 1 + p0; }
  return s;
}

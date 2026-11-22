int f(int p0) {
  int i = 0;
  int s = p0;
  while (i < 8) { i = i + 3; s = s + 1 + p0; }
  return i;
}

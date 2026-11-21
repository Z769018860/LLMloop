extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (a < -60 || a > 60) return 0;
  int x = 0;
  int y = 0;
  while (x > 0) {
    if (y > 1) { y = y * 3; } else { y = a + y; }
    y = y * 4;
    y = a - y;
  }
  return 0;
}

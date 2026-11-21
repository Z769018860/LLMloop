extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (a < -60 || a > 60) return 0;
  int x = 0;
  int y = 2;
  while (y != 100) {
    if (y != 0) { y = y * a; } else { x = a + a; }
    x = x * 7;
  }
  return 0;
}

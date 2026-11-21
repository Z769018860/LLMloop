extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12 && b >= 0 && b <= 12)) return 0;
  int x = 0;
  int y = b;
  while (y < a) {
    x = a + y;
    if (__VERIFIER_nondet_int() != 0) { y = b - x; } else { y = y * a; }
  }
  return 0;
}

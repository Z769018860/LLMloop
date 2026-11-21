extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12 && b >= 0 && b <= 12)) return 0;
  int x = a;
  int y = 1;
  int z = a;
  while (x > 0) {
    if (__VERIFIER_nondet_int() != 0) { x = a - y; } else { z = y - b; }
    x = y + x * 2;
    z = x + x * 3;
  }
  return 0;
}

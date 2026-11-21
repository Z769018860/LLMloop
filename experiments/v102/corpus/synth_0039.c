extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= -4 && a <= 4 && b >= -4 && b <= 4)) return 0;
  int x = 1;
  int y = 1;
  while (y != 0) {
    x = x - x;
    y = b + a;
    if (__VERIFIER_nondet_int() != 0) { x = x + 100; } else { y = y + 10; }
  }
  return 0;
}

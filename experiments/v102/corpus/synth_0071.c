extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 4 && b >= 0 && b <= 4)) return 0;
  int x = 2;
  int y = 2;
  while (x > 0) {
    if (__VERIFIER_nondet_int() != 0) { y = y * 7; } else { x = x * b; }
    y = x + y * a;
  }
  return 0;
}

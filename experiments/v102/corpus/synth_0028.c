extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12 && b >= 0 && b <= 12)) return 0;
  int x = 0;
  int y = 0;
  while (y > 0) {
    if (__VERIFIER_nondet_int() != 0) { x = x * a; } else { y = y + y * a; }
  }
  return 0;
}

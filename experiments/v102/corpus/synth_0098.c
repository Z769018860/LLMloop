extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12 && b >= 0 && b <= 12)) return 0;
  int x = 2;
  int y = 0;
  while (__VERIFIER_nondet_int() != 0) {
    if (__VERIFIER_nondet_int() != 0) { x = y + x * a; } else { x = y + x * 3; }
  }
  return 0;
}

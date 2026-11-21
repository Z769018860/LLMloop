extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (a < 0 || a > 40 || b < 0 || b > 40) return 0;
  int x = 1;
  int y = 2;
  while (__VERIFIER_nondet_int() != 0) {
    x = x + y * 2;
    y = x + y * 2;
    if (__VERIFIER_nondet_int() != 0) { x = y * 7; } else { y = x + y * 2; }
  }
  return 0;
}

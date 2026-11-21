extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 4)) return 0;
  int x = 1;
  int y = 0;
  while (x < 50 && __VERIFIER_nondet_int() != 0) {
    if (__VERIFIER_nondet_int() != 0) { x = x + x * 3; } else { y = y + y * 2; }
    x = x * 4;
  }
  return 0;
}

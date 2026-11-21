extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12)) return 0;
  int x = a;
  int y = 0;
  int z = a;
  while (x != 0) {
    if (__VERIFIER_nondet_int() != 0) { y = x + x * 3; } else { z = a - x; }
  }
  return 0;
}

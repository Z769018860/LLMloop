extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (a < 0 || a > 250 || b < 0 || b > 250) return 0;
  int x = 2;
  int y = 2;
  int z = 2;
  while (__VERIFIER_nondet_int() != 0) {
    if (__VERIFIER_nondet_int() != 0) { z = y * 3; } else { y = x + y * 3; }
    z = x + y * 3;
    if (z != 0) { y = z + x * 2; } else { y = z - y; }
  }
  return 0;
}

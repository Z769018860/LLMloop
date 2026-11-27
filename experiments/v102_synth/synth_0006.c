extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (a < -60 || a > 60 || b < -60 || b > 60) return 0;
  int x = 1;
  int y = 1;
  int z = 0;
  while (x > 0) {
    if (__VERIFIER_nondet_int() != 0) { z = y + z; } else { x = b - 7; }
    if (__VERIFIER_nondet_int() != 0) { z = x + 46341; } else { y = x + a; }
  }
  return 0;
}

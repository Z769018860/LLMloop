extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 8 && b >= 0 && b <= 8)) return 0;
  int x = a;
  int y = a;
  int z = 2;
  while (z < 50 && __VERIFIER_nondet_int() != 0) {
    if (__VERIFIER_nondet_int() != 0) { y = z * 4; } else { z = x * 4; }
    z = y + b;
  }
  return 0;
}

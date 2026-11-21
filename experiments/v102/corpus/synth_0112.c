extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 4 && b >= 0 && b <= 4)) return 0;
  int x = b;
  int y = a;
  int z = b;
  while (z < 5000 && __VERIFIER_nondet_int() != 0) {
    if (__VERIFIER_nondet_int() != 0) { z = z * 4; } else { z = b - 1000; }
    z = z * 2;
    y = b + a;
  }
  return 0;
}

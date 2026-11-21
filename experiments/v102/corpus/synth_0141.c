extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12)) return 0;
  int x = 0;
  int y = a;
  int z = 1;
  while (__VERIFIER_nondet_int() != 0) {
    if (__VERIFIER_nondet_int() != 0) { z = a - z; } else { z = z * 3; }
    z = a - y;
    z = x * 3;
  }
  return 0;
}

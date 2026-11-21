extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= -4 && a <= 4)) return 0;
  int x = 2;
  int y = a;
  int z = 2;
  while (__VERIFIER_nondet_int() != 0) {
    z = y * a;
    if (__VERIFIER_nondet_int() != 0) { z = y + a; } else { z = z * 3; }
  }
  return 0;
}

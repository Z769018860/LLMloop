extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 8)) return 0;
  int x = a;
  int y = 0;
  int z = 1;
  while (__VERIFIER_nondet_int() != 0) {
    x = y * 2;
    if (__VERIFIER_nondet_int() != 0) { z = y + z * 3; } else { x = z + y * 2; }
    z = y * 2;
  }
  return 0;
}

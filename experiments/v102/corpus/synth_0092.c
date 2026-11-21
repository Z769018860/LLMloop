extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12 && b >= 0 && b <= 12)) return 0;
  int x = 1;
  int y = b;
  int z = 1;
  while (x != 100) {
    if (__VERIFIER_nondet_int() != 0) { z = y * 4; } else { y = z + z; }
  }
  return 0;
}

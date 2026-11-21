extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 8 && b >= 0 && b <= 8)) return 0;
  int x = 1;
  int y = 2;
  int z = 2;
  while (y > 0) {
    z = x + z * 2;
    if (x > 1) { z = z + y * 3; } else { y = z + x * 3; }
    if (__VERIFIER_nondet_int() != 0) { x = z + z * a; } else { x = y * 7; }
  }
  return 0;
}

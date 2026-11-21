extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 8 && b >= 0 && b <= 8)) return 0;
  int x = b;
  int y = 0;
  int z = 0;
  while (z != 100) {
    y = a + z;
    x = y + z;
    if (y == 0) { x = y + y * 2; } else { z = y * 2; }
  }
  return 0;
}

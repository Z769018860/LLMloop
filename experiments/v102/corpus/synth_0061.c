extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 8 && b >= 0 && b <= 8)) return 0;
  int x = 1;
  int y = 0;
  int z = a;
  while (z != 100) {
    z = x + x * 2;
    if (z != b) { x = y + z * 3; } else { z = z - b; }
  }
  return 0;
}

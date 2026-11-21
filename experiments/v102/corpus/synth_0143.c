extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 4 && b >= 0 && b <= 4)) return 0;
  int x = 0;
  int y = 2;
  int z = 2;
  while (x != 0) {
    y = x + z;
    if (y > a) { x = x * b; } else { z = x + z * 2; }
  }
  return 0;
}

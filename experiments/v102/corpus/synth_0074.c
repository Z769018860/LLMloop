extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12 && b >= 0 && b <= 12)) return 0;
  int x = 1;
  int y = 2;
  int z = 0;
  while (y > 0) {
    z = z * 3;
    if (__VERIFIER_nondet_int() != 0) { x = b - 2; } else { y = z * 7; }
    y = z - y;
  }
  return 0;
}

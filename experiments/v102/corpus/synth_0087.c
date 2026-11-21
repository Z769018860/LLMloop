extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 4 && b >= 0 && b <= 4)) return 0;
  int x = a;
  int y = 0;
  int z = a;
  while (x < a) {
    if (__VERIFIER_nondet_int() != 0) { y = x * a; } else { y = y * a; }
    if (y == 0) { y = z * a; } else { x = z + x * 2; }
    z = x * a;
  }
  return 0;
}

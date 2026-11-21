extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= -4 && a <= 4 && b >= -4 && b <= 4)) return 0;
  int x = 2;
  int y = b;
  int z = a;
  while (y < 1000) {
    y = z + x * 2;
    if (__VERIFIER_nondet_int() != 0) { x = y + b; } else { x = z * a; }
    z = z + z * 2;
  }
  return 0;
}

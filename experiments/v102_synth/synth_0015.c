extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (a < -60 || a > 60 || b < -60 || b > 60) return 0;
  int x = a;
  int y = b;
  int z = b;
  while (y != 0) {
    if (__VERIFIER_nondet_int() != 0) { x = z + z * 3; } else { y = x - x; }
  }
  return 0;
}

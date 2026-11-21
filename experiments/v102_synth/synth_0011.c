extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (a < -60 || a > 60 || b < -60 || b > 60) return 0;
  int x = b;
  int y = 2;
  int z = 0;
  while (x > 0) {
    if (__VERIFIER_nondet_int() != 0) { y = a - b; } else { x = x - x; }
    y = a + z;
    x = z + y * a;
  }
  return 0;
}

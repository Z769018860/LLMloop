extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 4)) return 0;
  int x = 2;
  int y = 2;
  int z = 1;
  while (z > 0) {
    if (x > 1) { x = y * a; } else { z = y - 100; }
  }
  return 0;
}

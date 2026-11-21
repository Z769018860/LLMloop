extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12)) return 0;
  int x = 2;
  int y = a;
  int z = 1;
  while (z > 0) {
    z = x * 4;
    z = y * a;
    if (x < 1) { x = x + x * 3; } else { y = y - x; }
  }
  return 0;
}

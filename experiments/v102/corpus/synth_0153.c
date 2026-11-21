extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12)) return 0;
  int x = 0;
  int y = 1;
  int z = 2;
  while (z < 100) {
    y = y + x * 2;
    if (y == 0) { y = z * 2; } else { y = z - x; }
  }
  return 0;
}

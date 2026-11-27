extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (a < -60 || a > 60) return 0;
  int x = 2;
  int y = 1;
  int z = 0;
  while (x != 0) {
    x = y * 4;
    if (y > a) { y = x + 1; } else { x = x + y * 2; }
    if (__VERIFIER_nondet_int() != 0) { y = y - y; } else { z = y * 7; }
  }
  return 0;
}

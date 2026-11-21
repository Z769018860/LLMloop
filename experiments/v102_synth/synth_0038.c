extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (a < 0 || a > 40) return 0;
  int x = a;
  int y = a;
  int z = 2;
  while (z != 100) {
    if (__VERIFIER_nondet_int() != 0) { x = z - y; } else { z = y + z * 3; }
    if (x > 1) { x = x - a; } else { z = z + x * 2; }
    y = x * 3;
  }
  return 0;
}

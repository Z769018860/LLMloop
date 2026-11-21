extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= -4 && a <= 4)) return 0;
  int x = 1;
  int y = 1;
  int z = 2;
  while (x > 0) {
    z = x * 4;
    if (__VERIFIER_nondet_int() != 0) { x = y * 4; } else { z = z - y; }
    z = z + y * 3;
  }
  return 0;
}

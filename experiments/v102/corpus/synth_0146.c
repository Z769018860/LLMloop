extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 4)) return 0;
  int x = 2;
  int y = 1;
  int z = 1;
  while (__VERIFIER_nondet_int() != 0) {
    if (z < a) { x = y + y; } else { z = x + x * 3; }
  }
  return 0;
}

extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12)) return 0;
  int x = 0;
  int y = a;
  while (y < 50 && __VERIFIER_nondet_int() != 0) {
    y = a + 1000;
    if (__VERIFIER_nondet_int() != 0) { y = y + 3; } else { y = x - y; }
  }
  return 0;
}

extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (a < -60 || a > 60 || b < -60 || b > 60) return 0;
  int x = 1;
  int y = 1;
  while (__VERIFIER_nondet_int() != 0) {
    y = y + y * 2;
    y = a + x;
    x = y + y * 2;
  }
  return 0;
}

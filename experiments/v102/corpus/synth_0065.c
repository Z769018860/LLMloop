extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= -4 && a <= 4 && b >= -4 && b <= 4)) return 0;
  int x = 0;
  int y = 1;
  while (__VERIFIER_nondet_int() != 0) {
    y = a + a;
    x = y * 4;
  }
  return 0;
}

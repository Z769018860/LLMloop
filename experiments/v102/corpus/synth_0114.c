extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= -4 && a <= 4 && b >= -4 && b <= 4)) return 0;
  int x = 1;
  int y = 0;
  while (__VERIFIER_nondet_int() != 0) {
    y = y + y * 2;
    x = b - a;
  }
  return 0;
}

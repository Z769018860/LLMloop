extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 8 && b >= 0 && b <= 8)) return 0;
  int x = a;
  int y = 0;
  while (__VERIFIER_nondet_int() != 0) {
    x = b - b;
    y = b - y;
  }
  return 0;
}

extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 8 && b >= 0 && b <= 8)) return 0;
  int x = 1;
  int y = 1;
  while (__VERIFIER_nondet_int() != 0) {
    x = a - b;
    x = y + x * 3;
    x = b - 5;
  }
  return 0;
}

extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 4 && b >= 0 && b <= 4)) return 0;
  int x = 1;
  int y = a;
  while (__VERIFIER_nondet_int() != 0) {
    x = x * 2;
  }
  return 0;
}

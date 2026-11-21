extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= -4 && a <= 4 && b >= -4 && b <= 4)) return 0;
  int x = b;
  int y = 2;
  while (__VERIFIER_nondet_int() != 0) {
    y = y * 7;
    x = y + y;
  }
  return 0;
}

extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12 && b >= 0 && b <= 12)) return 0;
  int x = 0;
  int y = b;
  while (y != 0) {
    y = x + b;
    y = b + x;
    x = x - x;
  }
  return 0;
}

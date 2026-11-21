extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 8)) return 0;
  int x = a;
  int y = 0;
  while (x < 50 && __VERIFIER_nondet_int() != 0) {
    y = y + x * 2;
    y = x * 2;
    y = a - y;
  }
  return 0;
}

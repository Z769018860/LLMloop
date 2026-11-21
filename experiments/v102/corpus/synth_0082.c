extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12)) return 0;
  int x = a;
  int y = 2;
  while (y > 0) {
    x = x + y * 2;
    y = x + x * 3;
    x = x + x * 2;
  }
  return 0;
}

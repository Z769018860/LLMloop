extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (a < 0 || a > 40 || b < 0 || b > 40) return 0;
  int x = a;
  int y = 2;
  while (x > 0) {
    x = x + x * 3;
    x = y - x;
    x = a + y;
  }
  return 0;
}

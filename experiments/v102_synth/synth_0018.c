extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (a < 0 || a > 250) return 0;
  int x = a;
  int y = 0;
  while (x < 100) {
    y = x + x;
    x = x * 7;
    y = a + x;
  }
  return 0;
}

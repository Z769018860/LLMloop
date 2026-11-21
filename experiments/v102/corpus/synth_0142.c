extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12)) return 0;
  int x = a;
  int y = 0;
  while (y < a) {
    y = y + x * 2;
    y = a + x;
    x = y + y * 2;
  }
  return 0;
}

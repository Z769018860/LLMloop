extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= -4 && a <= 4)) return 0;
  int x = 1;
  int y = 0;
  while (x < 10) {
    x = a + 2;
  }
  return 0;
}

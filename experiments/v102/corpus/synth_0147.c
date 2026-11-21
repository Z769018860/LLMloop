extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= -4 && a <= 4)) return 0;
  int x = 0;
  int y = 2;
  while (x != 0) {
    y = a + a;
    y = y - 5;
  }
  return 0;
}

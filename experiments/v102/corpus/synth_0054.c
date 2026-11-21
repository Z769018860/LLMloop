extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12)) return 0;
  int x = a;
  int y = 1;
  while (x > 0) {
    x = y + 1;
    x = a - a;
  }
  return 0;
}

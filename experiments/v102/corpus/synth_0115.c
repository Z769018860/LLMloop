extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12)) return 0;
  int x = 1;
  int y = 2;
  int z = 2;
  while (x > 0) {
    z = y - a;
    x = y - a;
  }
  return 0;
}

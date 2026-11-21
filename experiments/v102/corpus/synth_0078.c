extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12)) return 0;
  int x = 1;
  int y = 0;
  int z = 0;
  while (x < 5000 && __VERIFIER_nondet_int() != 0) {
    z = a + x;
  }
  return 0;
}

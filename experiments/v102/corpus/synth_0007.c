extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= -4 && a <= 4)) return 0;
  int x = 1;
  int y = a;
  int z = 2;
  while (y < 50 && __VERIFIER_nondet_int() != 0) {
    y = a + x;
    x = z + x;
  }
  return 0;
}

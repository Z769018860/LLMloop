extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12)) return 0;
  int x = a;
  int y = 0;
  int z = 1;
  while (y > 0) {
    y = z * 7;
    z = a + x;
  }
  return 0;
}

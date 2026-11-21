extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 4)) return 0;
  int x = 0;
  int y = 2;
  int z = 2;
  while (y > 0) {
    z = x + y * 3;
    z = a + a;
  }
  return 0;
}

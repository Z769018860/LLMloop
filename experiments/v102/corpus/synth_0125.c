extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12)) return 0;
  int x = 0;
  int y = a;
  int z = a;
  while (x > 0) {
    z = x + z * 2;
    y = x + y * 3;
    z = x - a;
  }
  return 0;
}

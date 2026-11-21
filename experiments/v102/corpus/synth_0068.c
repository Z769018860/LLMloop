extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12)) return 0;
  int x = 1;
  int y = 2;
  int z = 1;
  while (__VERIFIER_nondet_int() != 0) {
    x = a - a;
    y = z - y;
    z = x - 2;
  }
  return 0;
}

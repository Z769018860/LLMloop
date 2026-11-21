extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12 && b >= 0 && b <= 12)) return 0;
  int x = a;
  int y = a;
  int z = 0;
  while (z < 50 && __VERIFIER_nondet_int() != 0) {
    x = b + a;
    y = z * 4;
  }
  return 0;
}

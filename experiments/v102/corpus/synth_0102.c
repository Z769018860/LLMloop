extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= -4 && a <= 4 && b >= -4 && b <= 4)) return 0;
  int x = 1;
  int y = 0;
  int z = 0;
  while (z < 5000 && __VERIFIER_nondet_int() != 0) {
    z = x + 65536;
  }
  return 0;
}

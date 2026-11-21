extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12 && b >= 0 && b <= 12)) return 0;
  int x = b;
  int y = 2;
  int z = b;
  while (z != 0) {
    y = y * 4;
  }
  return 0;
}

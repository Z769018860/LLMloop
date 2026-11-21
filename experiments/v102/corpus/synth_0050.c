extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 4 && b >= 0 && b <= 4)) return 0;
  int x = 2;
  int y = b;
  int z = 0;
  while (z != 0) {
    y = z * 2;
  }
  return 0;
}

extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 8 && b >= 0 && b <= 8)) return 0;
  int x = 2;
  int y = a;
  int z = b;
  while (x > 0) {
    z = z * 2;
  }
  return 0;
}

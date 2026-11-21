extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= -4 && a <= 4 && b >= -4 && b <= 4)) return 0;
  int x = a;
  int y = b;
  int z = a;
  while (z > 0) {
    x = b - y;
  }
  return 0;
}

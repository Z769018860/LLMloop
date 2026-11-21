extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 4 && b >= 0 && b <= 4)) return 0;
  int x = 0;
  int y = 0;
  int z = a;
  while (x > 0) {
    y = y - y;
    z = y * a;
  }
  return 0;
}

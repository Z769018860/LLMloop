extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= -4 && a <= 4 && b >= -4 && b <= 4)) return 0;
  int x = a;
  int y = a;
  int z = 1;
  while (__VERIFIER_nondet_int() != 0) {
    z = z * 4;
    x = x * 3;
  }
  return 0;
}

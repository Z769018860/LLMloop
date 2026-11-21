extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 8 && b >= 0 && b <= 8)) return 0;
  int x = 2;
  int y = b;
  int z = 0;
  while (__VERIFIER_nondet_int() != 0) {
    y = z + b;
    x = y + b;
  }
  return 0;
}

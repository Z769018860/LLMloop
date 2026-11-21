extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 8)) return 0;
  int x = 0;
  int y = 1;
  int z = 0;
  while (__VERIFIER_nondet_int() != 0) {
    x = y * 2;
    y = z - a;
  }
  return 0;
}

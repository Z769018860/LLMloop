extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (a < 0 || a > 40) return 0;
  int x = 1;
  int y = 2;
  int z = a;
  while (__VERIFIER_nondet_int() != 0) {
    x = y + a;
    z = x + a;
  }
  return 0;
}

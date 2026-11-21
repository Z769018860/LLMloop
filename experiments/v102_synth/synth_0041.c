extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (a < 0 || a > 40) return 0;
  int x = 2;
  int y = 2;
  int z = 1;
  while (__VERIFIER_nondet_int() != 0) {
    y = a - 1;
  }
  return 0;
}

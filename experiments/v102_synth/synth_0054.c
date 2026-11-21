extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (a < 0 || a > 120) return 0;
  int x = 1;
  int y = a;
  while (__VERIFIER_nondet_int() != 0) {
    x = a + y;
  }
  return 0;
}

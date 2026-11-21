extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (a < 0 || a > 250) return 0;
  int x = a;
  int y = 0;
  while (__VERIFIER_nondet_int() != 0) {
    x = y + y * 2;
    x = y * 4;
  }
  return 0;
}

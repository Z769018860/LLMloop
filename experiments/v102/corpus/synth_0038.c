extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 8)) return 0;
  int x = 1;
  int y = 1;
  while (__VERIFIER_nondet_int() != 0) {
    x = y + y;
    x = x * 3;
  }
  return 0;
}

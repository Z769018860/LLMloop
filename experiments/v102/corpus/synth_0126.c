extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 8)) return 0;
  int x = 2;
  int y = 1;
  while (__VERIFIER_nondet_int() != 0) {
    if (__VERIFIER_nondet_int() != 0) { x = x + y * 3; } else { y = y * 2; }
    y = x * 3;
  }
  return 0;
}

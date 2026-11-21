extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 4)) return 0;
  int x = 0;
  int y = 0;
  while (__VERIFIER_nondet_int() != 0) {
    if (__VERIFIER_nondet_int() != 0) { y = x * 4; } else { y = y * 7; }
  }
  return 0;
}

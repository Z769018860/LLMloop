extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (a < 0 || a > 40) return 0;
  int x = a;
  int y = 0;
  while (__VERIFIER_nondet_int() != 0) {
    y = y + y * 3;
    if (__VERIFIER_nondet_int() != 0) { x = y * 7; } else { y = x + y * 2; }
    x = x * 3;
  }
  return 0;
}

extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12 && b >= 0 && b <= 12)) return 0;
  int x = b;
  int y = b;
  while (x > 0) {
    if (y > 0) { y = x * 7; } else { y = x * 7; }
  }
  return 0;
}

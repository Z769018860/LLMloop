extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12 && b >= 0 && b <= 12)) return 0;
  int x = 1;
  int y = 1;
  while (y > 0) {
    if (y < b) { y = x - y; } else { y = y + y * 2; }
  }
  return 0;
}

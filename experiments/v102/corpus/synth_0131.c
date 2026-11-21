extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 4 && b >= 0 && b <= 4)) return 0;
  int x = b;
  int y = a;
  while (y > 0) {
    if (y > 1) { y = y + y * 2; } else { x = x * b; }
    y = y - y;
  }
  return 0;
}

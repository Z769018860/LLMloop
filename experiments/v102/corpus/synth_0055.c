extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= -4 && a <= 4 && b >= -4 && b <= 4)) return 0;
  int x = 2;
  int y = 0;
  while (y < 1000) {
    if (x != b) { x = x + x * 3; } else { y = y + x * 2; }
    if (__VERIFIER_nondet_int() != 0) { x = x + x * a; } else { x = y + x * a; }
    y = y + x;
  }
  return 0;
}

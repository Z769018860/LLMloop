extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 8 && b >= 0 && b <= 8)) return 0;
  int x = 1;
  int y = 1;
  while (y != 100) {
    y = y + y * 3;
    if (y == 0) { y = x - 3; } else { x = x + x * a; }
    if (y == 0) { y = y + y * 3; } else { y = y + x; }
  }
  return 0;
}

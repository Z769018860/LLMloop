extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 8 && b >= 0 && b <= 8)) return 0;
  int x = 1;
  int y = a;
  while (y < 10) {
    if (__VERIFIER_nondet_int() != 0) { x = y + y * a; } else { x = y + x; }
    y = y * 4;
    if (x == 1) { x = x * a; } else { x = x * b; }
  }
  return 0;
}

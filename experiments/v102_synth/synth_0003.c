extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (a < -60 || a > 60 || b < -60 || b > 60) return 0;
  int x = a;
  int y = 2;
  while (x < a) {
    y = y - x;
    if (__VERIFIER_nondet_int() != 0) { x = x - 10; } else { x = y + y * 3; }
  }
  return 0;
}

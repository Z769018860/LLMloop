extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= -4 && a <= 4 && b >= -4 && b <= 4)) return 0;
  int x = 2;
  int y = 1;
  while (x < 1000) {
    if (x == b) { x = a - b; } else { x = x + y * a; }
    y = y * 7;
    x = y + y * 3;
  }
  return 0;
}

extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (a < 0 || a > 250) return 0;
  int x = 2;
  int y = 0;
  while (x > 0) {
    if (y == a) { y = x * 4; } else { x = y + x * 3; }
    y = x - 2;
  }
  return 0;
}

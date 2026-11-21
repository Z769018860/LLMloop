extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (a < 0 || a > 40 || b < 0 || b > 40) return 0;
  int x = 2;
  int y = 1;
  while (y < a) {
    if (y < 0) { x = y * 2; } else { x = y + y; }
  }
  return 0;
}

extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (a < 0 || a > 40) return 0;
  int x = a;
  int y = 1;
  while (x < 100) {
    if (__VERIFIER_nondet_int() != 0) { x = y + x * 3; } else { x = x + y * 3; }
    x = x * 3;
  }
  return 0;
}

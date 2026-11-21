extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 8)) return 0;
  int x = 0;
  int y = 0;
  while (x < 50 && __VERIFIER_nondet_int() != 0) {
    if (y < 0) { x = y + y * 3; } else { x = a + 1; }
  }
  return 0;
}

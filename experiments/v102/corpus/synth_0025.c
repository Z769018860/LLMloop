extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 4)) return 0;
  int x = 0;
  int y = a;
  while (x < 50 && __VERIFIER_nondet_int() != 0) {
    if (x == a) { x = x + y * 3; } else { x = x * 4; }
    if (y < 1) { y = y + 5; } else { y = y * 3; }
  }
  return 0;
}

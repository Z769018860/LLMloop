extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12)) return 0;
  int x = 1;
  int y = a;
  while (x < 5000 && __VERIFIER_nondet_int() != 0) {
    if (y > a) { y = y * 7; } else { y = y * 7; }
    x = y - a;
  }
  return 0;
}

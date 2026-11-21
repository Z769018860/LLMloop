extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= -4 && a <= 4)) return 0;
  int x = 1;
  int y = a;
  while (x != 0) {
    if (__VERIFIER_nondet_int() != 0) { x = y * 2; } else { x = y + a; }
    x = x + 7;
    y = y * 2;
  }
  return 0;
}

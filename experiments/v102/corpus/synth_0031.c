extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 12)) return 0;
  int x = a;
  int y = a;
  int z = a;
  while (__VERIFIER_nondet_int() != 0) {
    y = y * a;
    z = x * 2;
    if (x > 0) { x = a - a; } else { y = x + a; }
  }
  return 0;
}

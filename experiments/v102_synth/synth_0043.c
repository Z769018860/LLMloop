extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (a < 0 || a > 40) return 0;
  int x = 1;
  int y = 1;
  int z = 0;
  while (__VERIFIER_nondet_int() != 0) {
    if (x > a) { y = x + a; } else { y = x + x; }
  }
  return 0;
}

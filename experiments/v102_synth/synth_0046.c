extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (a < -60 || a > 60) return 0;
  int x = 0;
  int y = a;
  int z = 2;
  while (__VERIFIER_nondet_int() != 0) {
    y = z + y;
    y = x + x;
  }
  return 0;
}

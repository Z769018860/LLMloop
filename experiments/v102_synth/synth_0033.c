extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (a < -60 || a > 60) return 0;
  int x = 2;
  int y = a;
  int z = a;
  while (__VERIFIER_nondet_int() != 0) {
    z = y * 4;
    z = z - x;
  }
  return 0;
}

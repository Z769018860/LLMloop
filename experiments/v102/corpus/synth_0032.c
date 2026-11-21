extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= -4 && a <= 4)) return 0;
  int x = 1;
  int y = 1;
  int z = 2;
  while (__VERIFIER_nondet_int() != 0) {
    y = y - z;
    y = z * 3;
  }
  return 0;
}

extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= -4 && a <= 4)) return 0;
  int x = 0;
  int y = 1;
  int z = 1;
  while (__VERIFIER_nondet_int() != 0) {
    z = y + y * 3;
  }
  return 0;
}

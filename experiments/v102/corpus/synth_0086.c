extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= -4 && a <= 4)) return 0;
  int x = 1;
  int y = 1;
  int z = 0;
  while (x > 0) {
    x = x + z * 3;
  }
  return 0;
}

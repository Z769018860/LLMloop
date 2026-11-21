extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= -4 && a <= 4)) return 0;
  int x = 2;
  int y = 1;
  int z = a;
  while (z < 5000 && __VERIFIER_nondet_int() != 0) {
    x = x * 7;
    y = y * 7;
  }
  return 0;
}

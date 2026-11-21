extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 8)) return 0;
  int x = a;
  int y = 0;
  int z = a;
  while (x < 50 && __VERIFIER_nondet_int() != 0) {
    x = z * 3;
    y = z + z;
    z = a - 3;
  }
  return 0;
}

extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 8)) return 0;
  int x = 2;
  int y = 2;
  int z = 1;
  while (z < 1000) {
    x = z + z * 3;
    y = x * 7;
    x = a - a;
  }
  return 0;
}

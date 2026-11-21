extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= -4 && a <= 4 && b >= -4 && b <= 4)) return 0;
  int x = 1;
  int y = b;
  int z = a;
  while (y < 1000) {
    z = z + z * 3;
    y = z * 2;
    x = y * 7;
  }
  return 0;
}

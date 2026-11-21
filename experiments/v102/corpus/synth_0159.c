extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 8 && b >= 0 && b <= 8)) return 0;
  int x = 0;
  int y = 1;
  int z = b;
  while (y > 0) {
    x = y + y * 3;
  }
  return 0;
}

extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 4 && b >= 0 && b <= 4)) return 0;
  int x = 1;
  int y = 0;
  int z = 1;
  while (y > 0) {
    z = z * 7;
    x = x - z;
    if (z < a) { y = x + y * 2; } else { z = b - z; }
  }
  return 0;
}

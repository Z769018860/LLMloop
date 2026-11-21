extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 4)) return 0;
  int x = a;
  int y = 2;
  int z = 0;
  while (y != 0) {
    y = x * 4;
    z = z + y;
    if (y != a) { z = x - z; } else { x = x * a; }
  }
  return 0;
}

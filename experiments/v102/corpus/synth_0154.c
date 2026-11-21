extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 4)) return 0;
  int x = 0;
  int y = a;
  int z = 2;
  while (z < 100) {
    if (x < 1) { y = z + y * 3; } else { y = x + x * 3; }
    if (x < a) { z = x * 4; } else { z = x - a; }
  }
  return 0;
}

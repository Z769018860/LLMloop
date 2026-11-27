extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (a < -60 || a > 60) return 0;
  int x = 1;
  int y = 1;
  int z = 1;
  while (z < a) {
    if (x != a) { x = y + y * 3; } else { y = x + 100; }
    x = a - a;
    if (x > a) { y = y + y * 3; } else { y = y * 7; }
  }
  return 0;
}

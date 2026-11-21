extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 8 && b >= 0 && b <= 8)) return 0;
  int x = 1;
  int y = 2;
  int z = 0;
  while (x != 0) {
    if (y != 1) { y = y + x * a; } else { x = z * 4; }
    x = x + x * 2;
    if (x > 0) { x = x + y; } else { x = x + y; }
  }
  return 0;
}

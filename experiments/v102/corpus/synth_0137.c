extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= -4 && a <= 4 && b >= -4 && b <= 4)) return 0;
  int x = 1;
  int y = 0;
  int z = a;
  while (x > 0) {
    y = x * 7;
    if (x > a) { x = b - z; } else { y = z + y * 2; }
    if (__VERIFIER_nondet_int() != 0) { x = y + x; } else { x = x + b; }
  }
  return 0;
}

extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  int b = __VERIFIER_nondet_int();
  if (!(a >= 0 && a <= 8 && b >= 0 && b <= 8)) return 0;
  int x = 2;
  int y = a;
  int z = b;
  while (y > 0) {
    if (y < 0) { y = z + z * a; } else { y = y * 3; }
    z = x * 2;
    x = b + b;
  }
  return 0;
}

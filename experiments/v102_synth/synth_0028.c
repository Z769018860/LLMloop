extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (a < -60 || a > 60) return 0;
  int x = 2;
  int y = 1;
  while (x > 0) {
    y = a - x;
    if (__VERIFIER_nondet_int() != 0) { y = y - 65536; } else { y = x + x * 3; }
  }
  return 0;
}

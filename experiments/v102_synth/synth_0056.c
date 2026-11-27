extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (a < -60 || a > 60) return 0;
  int x = 2;
  int y = 1;
  int z = 2;
  while (x > 0) {
    y = z * 3;
    if (y < 1) { y = y + y; } else { x = z * 4; }
  }
  return 0;
}

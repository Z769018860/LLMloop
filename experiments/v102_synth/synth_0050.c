extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (a < 0 || a > 120) return 0;
  int x = a;
  int y = 0;
  while (y < 1000) {
    y = y + y * 2;
  }
  return 0;
}

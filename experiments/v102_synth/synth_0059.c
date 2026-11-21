extern int __VERIFIER_nondet_int(void);
int main() {
  int a = __VERIFIER_nondet_int();
  if (a < 0 || a > 40) return 0;
  int x = 2;
  int y = 0;
  while (x != 0) {
    x = a - x;
  }
  return 0;
}

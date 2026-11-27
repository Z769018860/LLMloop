int f(int x1__in, int x2__in){
int x2 = x2__in;
int x1 = x1__in;
while (x1 <= 10)
{
  x2 = 10;
  while (x2 > 1)
  {
    x2 = x2 - 1;
  }

  x1 = x1 + 1;
}

return 0;
}
extern int __VERIFIER_nondet_int(void);
extern void __VERIFIER_assume(int);
int main(void){
  int a0 = __VERIFIER_nondet_int();
  __VERIFIER_assume(a0 >= -2147483648 && a0 <= 2147483647);
  int a1 = __VERIFIER_nondet_int();
  __VERIFIER_assume(a1 >= -2147483648 && a1 <= 2147483647);
  return f(a0, a1);
}

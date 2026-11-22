int f(int x__in, int y__in){
int y = y__in;
int x = x__in;
while ((x > 0) && (y > 0))
{
  if (__VERIFIER_nondet_int() != 0)
  {
    x = x - 1;
    y = __VERIFIER_nondet_int();
  }
  else
  {
    y = y - 1;
  }
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

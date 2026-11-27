int f(int x__in, int y__in, int z){
int y = y__in;
int x = x__in;
int c = 0;
while ((x > z) || (y > z))
{
  if (x > z)
  {
    x = x - 1;
  }
  else
  {
    if (y > z)
    {
      y = y - 1;
    }
    else
    {
    }
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
  int a2 = __VERIFIER_nondet_int();
  __VERIFIER_assume(a2 >= -2147483648 && a2 <= 2147483647);
  return f(a0, a1, a2);
}

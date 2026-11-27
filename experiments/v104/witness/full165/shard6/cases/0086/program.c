int f(int i__in){
int i = i__in;
while (i != 0)
{
  if (((-5) <= i) && (i <= 35))
  {
    if (i < 0)
    {
      i = -5;
    }
    else
    {
      if (i > 30)
      {
        i = 35;
      }
      else
      {
        i = i - 1;
      }
    }
  }
  else
  {
    i = 0;
  }
}

return 0;
}
extern int __VERIFIER_nondet_int(void);
extern void __VERIFIER_assume(int);
int main(void){
  int a0 = __VERIFIER_nondet_int();
  __VERIFIER_assume(a0 >= -2147483648 && a0 <= 2147483647);
  return f(a0);
}

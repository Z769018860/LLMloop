int f(int x__in, int y){
int x = x__in;
int ytmp = 0;
int res = 0;
while ((x >= y) && (y > 0))
{
  ytmp = y;
  while (ytmp != 0)
  {
    if (ytmp > 0)
    {
      ytmp = ytmp - 1;
      x = x - 1;
    }
    else
    {
      ytmp = ytmp + 1;
      x = x + 1;
    }
  }

  res = res + 1;
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

int f(int i__in){
int i = i__in;
int up = 0;
while (i > 0)
{
  if (i == 1)
  {
    up = 1;
  }
  if (i == 10)
  {
    up = 0;
  }
  if (up == 1)
  {
    i = i + 1;
  }
  else
  {
    i = i - 1;
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

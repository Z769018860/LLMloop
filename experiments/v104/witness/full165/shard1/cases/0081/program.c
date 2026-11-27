int f(int x__in){
int x = x__in;
int xtmp = 0;
int res = 0;
int restmp = 0;
while (x > 1)
{
  xtmp = x - 2;
  restmp = 0;
  while (xtmp > 1)
  {
    xtmp = xtmp - 2;
    restmp = restmp + 1;
  }

  x = xtmp + 1;
  res = res + 1;
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

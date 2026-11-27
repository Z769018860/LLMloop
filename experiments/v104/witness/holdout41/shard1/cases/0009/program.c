int f(int x__in){
int x = x__in;
int y = 1;
while (x > 0)
{
  x = x - y;
  y = y + 1;
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

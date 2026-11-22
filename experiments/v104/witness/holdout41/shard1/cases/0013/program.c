int f(int __z){
int x = 0;
int y = 0;
while (y >= 0)
{
  if (x <= 50)
  {
    y = y + 1;
  }
  else
  {
    y = y - 1;
  }
  x = x + 1;
}

return 0;
}
extern int __VERIFIER_nondet_int(void);
extern void __VERIFIER_assume(int);
int main(void){
  int a0 = __VERIFIER_nondet_int();
  __VERIFIER_assume(a0 >= 0 && a0 <= 0);
  return f(a0);
}

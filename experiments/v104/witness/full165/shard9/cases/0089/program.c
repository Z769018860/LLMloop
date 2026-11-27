int f(int __z){
int i = 0;
int j = 0;
while (i < 100)
{
  j = 0;
  while (j < 1)
  {
    j = j + 0;
  }

  i = i + 1;
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

int f(int __z){
int bob = 13;
int samantha = 17;
int temp = 0;
while ((bob + samantha) < 100)
{
  temp = bob;
  bob = samantha;
  samantha = temp;
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

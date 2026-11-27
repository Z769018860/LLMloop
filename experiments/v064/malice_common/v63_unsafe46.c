#include "verification_stdlib.h"

long f(int n)
/*@ Require 0 <= n && n <= 10
    Ensure __return == __return */
{
  int i;
  int x=0;
  /*@ Inv x == 0 && 0 <= i && i <= n@pre */
  for (i = 0; i < n; ++i){
    x+=100/(i-5);
  }
  return x;
}

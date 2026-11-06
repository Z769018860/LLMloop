#include "verification_stdlib.h"

int f(int n)
/*@ Require 0 <= n && n <= 5
    Ensure __return == __return */
{
  int i;
  int x=0;
  /*@ Inv 0 <= x && 0 <= i && i <= n@pre */
  for (i = 0; i < n; ++i){
    x+=1000000000;
  }
  return x;
}

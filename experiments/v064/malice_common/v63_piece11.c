#include "verification_stdlib.h"

int f(int n)
/*@ Require 0 <= n && n <= 10000000
    Ensure __return == __return */
{
  int i;
  int x=53899;
  /*@ Inv 0 <= x && x <= 53899 && 0 <= i && i <= n@pre */
  for (i = 0; i < n; ++i){
    if(x>=9){
      x-=9;
    }
  }
  return x;
}

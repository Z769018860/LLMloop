#include "verification_stdlib.h"

int f(int n)
/*@ Require 0 <= n && n <= 2000000
    Ensure (n <= 1000000 && __return == 1000000 - n) || (n > 1000000 && __return == 0) */
{
  int i;
  int x=1000000;
  /*@ Inv 0 <= i && i <= n@pre && ((i <= 1000000 && x == 1000000 - i) || (i > 1000000 && x == 0)) */
  for (i = 0; i < n; ++i){
    if(x>0){
      x--;
    }
  }
  return x;
}

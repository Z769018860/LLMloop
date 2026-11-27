#include "verification_stdlib.h"

int f(int n)
/*@ Require 0 <= n && n <= 10000000
    Ensure __return == __return */
{
  int i;
  int x=11789;
  /*@ Inv 0 <= x && x <= 11789 && 0 <= i && i <= n@pre */
  for (i = 0; i < n; ++i){
    if(x>=6){
      x-=6;
    }
  }
  return x;
}

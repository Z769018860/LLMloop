#include "verification_stdlib.h"

int f(int n)
/*@ Require 0 <= n && n <= 10000000
    Ensure (n <= 1964 && __return == 11789 - 6 * n) || (n > 1964 && __return == 11789 - 11784) */
{
  int i;
  int x=11789;
  /*@ Inv 0 <= i && i <= n@pre && ((i <= 1964 && x == 11789 - 6 * i) || (i > 1964 && x == 11789 - 11784)) */
  for (i = 0; i < n; ++i){
    if(x>=6){
      x-=6;
    }
  }
  return x;
}

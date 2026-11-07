#include "verification_stdlib.h"

int f(int n)
/*@ Require 0 <= n && n <= 10000000
    Ensure (n <= 5988 && __return == 53899 - 9 * n) || (n > 5988 && __return == 53899 - 53892) */
{
  int i;
  int x=53899;
  /*@ Inv 0 <= i && i <= n@pre && ((i <= 5988 && x == 53899 - 9 * i) || (i > 5988 && x == 53899 - 53892)) */
  for (i = 0; i < n; ++i){
    if(x>=9){
      x-=9;
    }
  }
  return x;
}

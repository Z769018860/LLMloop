#include "verification_stdlib.h"

long f(int n)
/*@ Require 0 <= n && n <= 20000000
    Ensure __return == __return */
{
  int i;
  long x=n;
  /*@ Inv x == n@pre - i && 0 <= i && i <= n@pre */
  for (i = 0; i < n; ++i){
    x--;
  }
  return x;
}

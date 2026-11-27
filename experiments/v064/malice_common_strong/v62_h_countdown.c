#include "verification_stdlib.h"

long f(int n)
/*@ Require 0 <= n && n <= 20000000
    Ensure __return == 0 */
{
  int i;
  long x=n;
  /*@ Inv 0 <= i && i <= n@pre && (x == n@pre - i) */
  for (i = 0; i < n; ++i){
    x--;
  }
  return x;
}

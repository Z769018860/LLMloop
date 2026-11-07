#include "verification_stdlib.h"

long f(int n)
/*@ Require 0 <= n && n <= 30000
    Ensure __return == n * (n + 1) + 2 * n */
{
  int i;
  int a=0;
  long b=0;
  /*@ Inv 0 <= i && i <= n@pre && (a == 2 * i && b == i * (i + 1)) */
  for (i = 0; i < n; ++i){
    a+=2;
    b+=a;
  }
  return b+a;
}

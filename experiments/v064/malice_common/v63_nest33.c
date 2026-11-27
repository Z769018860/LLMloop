#include "verification_stdlib.h"

long f(int n)
/*@ Require 0 <= n && n <= 4000
    Ensure __return == __return */
{
  int i;
  int j;
  long x=0;
  /*@ Inv 0 <= x && x <= 4000 * i && 0 <= i && i <= n@pre */
  for (i = 0; i < n; ++i){
  /*@ Inv 0 <= x && x <= 4000 * i + j && 0 <= j && j <= n@pre - i && 0 <= i && i < n@pre */
    for (j = 0; j < n-i; ++j){
      x++;
    }
  }
  return x;
}

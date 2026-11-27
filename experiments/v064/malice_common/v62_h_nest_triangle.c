#include "verification_stdlib.h"

long f(int n)
/*@ Require 0 <= n && n <= 5000
    Ensure __return == __return */
{
  int i;
  int j;
  long x=0;
  /*@ Inv 0 <= x && x <= 5000 * i && 0 <= i && i <= n@pre */
  for (i = 0; i < n; ++i){
  /*@ Inv 0 <= x && x <= 5000 * i + j && 0 <= j && j <= i && 0 <= i && i < n@pre */
    for (j = 0; j < i; ++j){
      x++;
    }
  }
  return x;
}

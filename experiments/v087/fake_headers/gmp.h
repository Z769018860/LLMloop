/* minimal stand-in for GMP types used by coreutils factor/basenc (declarations only) */
#include <stddef.h>
typedef unsigned long mp_limb_t; typedef long mp_size_t; typedef unsigned long mp_bitcnt_t;
typedef struct { int _mp_alloc; int _mp_size; mp_limb_t *_mp_d; } __mpz_struct;
typedef __mpz_struct mpz_t[1]; typedef __mpz_struct *mpz_ptr; typedef const __mpz_struct *mpz_srcptr;

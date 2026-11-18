/* fallback-only stand-ins for project headers/macros; declarations only, no behaviour */
#include <stddef.h>
#include <stdint.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <time.h>
#include <unistd.h>
#include <signal.h>
#include <wchar.h>
#include <obstack.h>
typedef struct tm_zone *timezone_t;
extern timezone_t tzalloc(const char *);
extern void tzfree(timezone_t);
extern struct tm *localtime_rz(timezone_t, const time_t *, struct tm *);
extern time_t mktime_z(timezone_t, struct tm *);
extern void *xzalloc(size_t);
extern void *xnmalloc(size_t, size_t);
extern void *xinmalloc(ptrdiff_t, ptrdiff_t);
extern char *file_name_concat(const char *, const char *, char **);
extern char *dir_name(const char *);
extern int sig2str(int, char *);
extern int str2sig(const char *, int *);
extern int lchmodat(int, const char *, mode_t);
extern int lchownat(int, const char *, uid_t, gid_t);
extern int mbscasecmp(const char *, const char *);
extern void verror(int, int, const char *, __builtin_va_list);
#ifndef S_IRWXUGO
# define S_IRWXUGO (S_IRWXU | S_IRWXG | S_IRWXO)
#endif
#define SIG2STR_MAX 32
#define SETLOCALE_NULL_MAX 257
#define IDX_MAX PTRDIFF_MAX
#define LINK_FOLLOWS_SYMLINKS 1
#define EXEEXT ""
#define BOURNE_SHELL "/bin/sh"
#define O_NOLINKS 0
#define O_TEXT 0
#define O_SEARCH O_PATH
#define HAVE_WORKING_O_NOFOLLOW 1
#define MAX(a, b) ((a) > (b) ? (a) : (b))
#define MIN(a, b) ((a) < (b) ? (a) : (b))
#ifndef _GL_GNUC_PREREQ
# define _GL_GNUC_PREREQ(a, b) 0
#endif
#define GETGROUPS_T gid_t

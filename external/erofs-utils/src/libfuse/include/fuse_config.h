#ifndef LIBFUSE_CONFIG_H
#define LIBFUSE_CONFIG_H

#if defined(ANDROID) || defined(_ANDROID_)
#define pthread_setcancelstate(x, y)
#define pthread_cancel(c)
#endif

#define PACKAGE_VERSION "3.16.2"

#define HAVE_COPY_FILE_RANGE 1

#define HAVE_FALLOCATE 1

#define HAVE_FDATASYNC 1

#define HAVE_FORK 1

#define HAVE_FSTATAT 1

#define HAVE_ICONV 1

#define HAVE_OPENAT 1

#define HAVE_PIPE2 1

#define HAVE_POSIX_FALLOCATE 1

#define HAVE_READLINKAT 1

#define HAVE_SETXATTR 1

#define HAVE_SPLICE 1

#define HAVE_STRUCT_STAT_ST_ATIM 1

/* #undef HAVE_STRUCT_STAT_ST_ATIMESPEC */

#define HAVE_UTIMENSAT 1

#define HAVE_VMSPLICE 1

#endif // LIBFUSE_CONFIG_H

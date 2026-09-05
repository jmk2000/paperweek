#ifndef PW_MIN_STRING
#define PW_MIN_STRING
#include <stddef.h>
size_t strlen(const char *s);
int strcmp(const char *a,const char *b);
void *memcpy(void *to,const void *from,size_t n);
void *memmove(void *to,const void *from,size_t n);
void *memset(void *to,int c,size_t n);
#endif

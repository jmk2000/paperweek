/* Only for the portable preview build. Emscripten/native builds use libc.
 * Intentionally bounded formatter: %s, %d, %u, %% and zero-padded integers. */
#include <stddef.h>
#include <stdarg.h>
size_t strlen(const char *s){size_t n=0;while(s[n])++n;return n;}
int strcmp(const char *a,const char *b){while(*a&&*a==*b){++a;++b;}return (unsigned char)*a-(unsigned char)*b;}
void *memcpy(void *to,const void *from,size_t n){unsigned char *a=to;const unsigned char *b=from;for(size_t i=0;i<n;++i)a[i]=b[i];return to;}
void *memset(void *to,int c,size_t n){unsigned char *a=to;for(size_t i=0;i<n;++i)a[i]=(unsigned char)c;return to;}
void *memmove(void *to,const void *from,size_t n){unsigned char *a=to;const unsigned char *b=from;if(a<b)for(size_t i=0;i<n;++i)a[i]=b[i];else for(size_t i=n;i>0;--i)a[i-1]=b[i-1];return to;}
static void put(char *out,size_t cap,size_t *n,char c){if(*n+1<cap)out[*n]=c;++*n;}
int snprintf(char *out,size_t cap,const char *fmt,...){
    va_list ap;va_start(ap,fmt);size_t n=0;
    for(;*fmt;++fmt){
        if(*fmt!='%'){put(out,cap,&n,*fmt);continue;}
        ++fmt;if(*fmt=='%'){put(out,cap,&n,'%');continue;}
        int width=0;char pad=' ';if(*fmt=='0'){pad='0';++fmt;}
        while(*fmt>='0'&&*fmt<='9'){width=width*10+*fmt-'0';++fmt;}if(width>32)width=32;
        if(*fmt=='s'){const char *s=va_arg(ap,const char *);if(!s)s="";while(*s)put(out,cap,&n,*s++);}
        else if(*fmt=='d'||*fmt=='u'){
            unsigned v;int negative=0;
            if(*fmt=='d'){int d=va_arg(ap,int);negative=d<0;v=negative?0U-(unsigned)d:(unsigned)d;}else v=va_arg(ap,unsigned);
            char digits[16];int len=0;do{digits[len++]=(char)('0'+v%10);v/=10;}while(v);
            if(negative)put(out,cap,&n,'-');
            for(int i=len+negative;i<width;++i)put(out,cap,&n,pad);
            while(len)put(out,cap,&n,digits[--len]);
        }else if(!*fmt)break;else put(out,cap,&n,'?');
    }
    va_end(ap);if(cap)out[n<cap?n:cap-1]=0;return (int)n;
}

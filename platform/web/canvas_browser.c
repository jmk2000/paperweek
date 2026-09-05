/* Fast dependency-free preview adapter. The actual layout and calendar engine
 * are compiled C/WASM; only the text rasterisation uses the browser's font.
 * This is NOT LVGL. Select the lvgl build for pixel-level LVGL parity. */
#include "canvas.h"
#include "calendar_ui.h"
#define IMPORT(name) __attribute__((import_module("paperweek"), import_name(name)))
IMPORT("begin") void web_begin(int paper);
IMPORT("rect") void web_rect(int x,int y,int w,int h,unsigned rgb);
IMPORT("text") void web_text(int x,int y,int w,int h,const char *text,int size,unsigned rgb,int align);
IMPORT("end") void web_end(void);
static bool paper;
void pw_platform_init(void){}
void pw_platform_present(void){}
void pw_draw_begin(bool p){paper=p;web_begin(p);}
void pw_draw_rect(int x,int y,int w,int h,pw_colour c){web_rect(x,y,w,h,pw_palette_rgb(c,paper));}
void pw_draw_text(int x,int y,int w,int h,const char *text,int size,pw_colour c,int align){web_text(x,y,w,h,text,size,pw_palette_rgb(c,paper),align);}
void pw_draw_end(void){web_end();}

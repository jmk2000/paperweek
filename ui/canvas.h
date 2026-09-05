#ifndef PAPERWEEK_CANVAS_H
#define PAPERWEEK_CANVAS_H
#include "view_model.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Same C layout calls either LVGL or the dependency-free SVG review exporter. */
void pw_draw_begin(bool paper);
void pw_draw_rect(int x, int y, int w, int h, pw_colour colour);
void pw_draw_text(int x, int y, int w, int h, const char *text, int size, pw_colour colour, int align);
void pw_draw_end(void);
#ifdef __cplusplus
}
#endif
#endif

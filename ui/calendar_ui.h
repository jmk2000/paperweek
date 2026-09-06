#ifndef PAPERWEEK_CALENDAR_UI_H
#define PAPERWEEK_CALENDAR_UI_H
#include "view_model.h"
#ifdef __cplusplus
extern "C" {
#endif
void pw_ui_web_size(int height,int width);
void pw_ui_render(const pw_view *view, bool paper_palette);
void pw_ui_render_ex(const pw_view *view, bool paper_palette, bool overlay_open, bool persistent_labels);
void pw_ui_refresh_placeholder(bool paper_palette);
uint32_t pw_palette_rgb(pw_colour colour, bool paper_palette);
#ifdef __cplusplus
}
#endif
#endif

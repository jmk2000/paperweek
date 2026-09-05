#ifndef PAPERWEEK_CALENDAR_UI_H
#define PAPERWEEK_CALENDAR_UI_H
#include "view_model.h"
#ifdef __cplusplus
extern "C" {
#endif
/* These are the UI entry points to reuse in the eventual firmware. */
void pw_ui_render(const pw_view *view, bool paper_palette);
uint32_t pw_palette_rgb(pw_colour colour, bool paper_palette);
#ifdef __cplusplus
}
#endif
#endif

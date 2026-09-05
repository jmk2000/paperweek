#include "calendar_ui.h"
#include "lvgl.h"
#include <stdio.h>
#include <string.h>

/* Representative RGB colours only: this is NOT a calibrated Spectra 6 simulation. */
uint32_t pw_palette_rgb(pw_colour colour, bool paper) {
    static const uint32_t reflective[] = {0x20211e, 0xf5f3e9, 0xad332b, 0xd6b633, 0x365889, 0x3e704e};
    static const uint32_t clean[] = {0x111111, 0xffffff, 0xc93028, 0xeacb23, 0x285bbb, 0x27834b};
    unsigned i = (unsigned)colour;
    if (i >= 6) i = PW_BLACK;
    return paper ? reflective[i] : clean[i];
}
static bool paper;
static lv_color_t ink(pw_colour c) { return lv_color_hex(pw_palette_rgb(c, paper)); }
static lv_obj_t *block(lv_obj_t *parent, int x, int y, int w, int h, pw_colour c) {
    lv_obj_t *obj = lv_obj_create(parent);
    lv_obj_remove_style_all(obj);
    lv_obj_remove_flag(obj, LV_OBJ_FLAG_SCROLLABLE | LV_OBJ_FLAG_CLICKABLE);
    lv_obj_set_pos(obj, x, y);
    lv_obj_set_size(obj, w, h);
    lv_obj_set_style_bg_color(obj, ink(c), 0);
    lv_obj_set_style_bg_opa(obj, LV_OPA_COVER, 0);
    return obj;
}
static lv_obj_t *text(lv_obj_t *parent, int x, int y, int w, int h,
                     const char *value, const lv_font_t *font, pw_colour c) {
    lv_obj_t *label = lv_label_create(parent);
    lv_obj_remove_style_all(label);
    lv_obj_set_pos(label, x, y);
    lv_obj_set_size(label, w, h);
    lv_obj_set_style_text_font(label, font, 0);
    lv_obj_set_style_text_color(label, ink(c), 0);
    lv_obj_set_style_text_line_space(label, 3, 0);
    lv_label_set_long_mode(label, LV_LABEL_LONG_MODE_DOTS);
    lv_label_set_text(label, value);
    return label;
}
static void right_text(lv_obj_t *root, int x, int y, int w, int h, const char *value,
                       const lv_font_t *font) {
    lv_obj_t *label = text(root, x, y, w, h, value, font, PW_BLACK);
    lv_obj_set_style_text_align(label, LV_TEXT_ALIGN_RIGHT, 0);
}
void pw_ui_render(const pw_view *view, bool paper_palette) {
    paper = paper_palette;
    lv_obj_t *root = lv_screen_active();
    lv_obj_clean(root);
    lv_obj_remove_style_all(root);
    lv_obj_set_size(root, PW_WIDTH, PW_HEIGHT);
    lv_obj_set_pos(root, 0, 0);
    lv_obj_remove_flag(root, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_bg_color(root, ink(PW_WHITE), 0);
    lv_obj_set_style_bg_opa(root, LV_OPA_COVER, 0);

    text(root, 48, 30, 480, 28, "P A P E R W E E K  /  FAMILY CALENDAR", &lv_font_montserrat_16, PW_BLACK);
    block(root, 1394, 35, 34, 7, PW_BLUE);
    block(root, 1434, 35, 34, 7, PW_RED);
    block(root, 1474, 35, 34, 7, PW_YELLOW);
    block(root, 1514, 35, 34, 7, PW_GREEN);
    text(root, 45, 69, 870, 64, view->title, &lv_font_montserrat_48, PW_BLACK);
    text(root, 48, 142, 810, 32, view->span, &lv_font_montserrat_24, PW_BLACK);
    right_text(root, 830, 76, 718, 42, view->month, &lv_font_montserrat_32);
    right_text(root, 940, 126, 608, 30, view->today, &lv_font_montserrat_20);
    right_text(root, 1328, 163, 220, 24, view->week_number, &lv_font_montserrat_16);

    const int legend_width = view->calendar_count ? 1500 / (int)view->calendar_count : 250;
    for (unsigned i = 0; i < view->calendar_count; ++i) {
        int x = 48 + (int)i * legend_width;
        block(root, x, 200, 12, 12, view->calendars[i].colour);
        text(root, x + 22, 193, legend_width - 40, 30, view->calendars[i].name,
             &lv_font_montserrat_20, PW_BLACK);
    }
    block(root, 48, 237, 1500, 2, PW_BLACK);

    for (int d = 0; d < PW_DAYS; ++d) {
        const pw_day *day = &view->days[d];
        int x = 48 + d * 214;
        if (d > 0) block(root, x - 12, 258, 1, 807, PW_BLACK);
        text(root, x, 269, 96, 28, day->dow, &lv_font_montserrat_20, PW_BLACK);
        if (day->today) {
            block(root, x + 103, 267, 80, 29, PW_BLACK);
            text(root, x + 113, 273, 63, 21, "TODAY", &lv_font_montserrat_14, PW_WHITE);
        }
        text(root, x - 2, 306, 113, 58, day->number, &lv_font_montserrat_40, PW_BLACK);
        text(root, x + 108, 330, 76, 28, day->month, &lv_font_montserrat_16, PW_BLACK);
        block(root, x, 382, 188, day->today ? 4 : 1, PW_BLACK);
        if (day->count == 0) {
            text(root, x + 1, 422, 172, 64, (strcmp(view->mode, "unavailable") == 0 ? "Calendar not\nloaded yet." : "No plans on\nthe calendar."), &lv_font_montserrat_20, PW_BLACK);
        }
        for (unsigned n = 0; n < day->count; ++n) {
            const pw_item *item = &day->items[n];
            int y = 410 + (int)n * 104;
            block(root, x, y + 1, 5, 93, item->colour);
            text(root, x + 14, y, 176, 25, item->time, &lv_font_montserrat_20, PW_BLACK);
            text(root, x + 14, y + 27, 176, 54, item->title, &lv_font_montserrat_24, PW_BLACK);
            text(root, x + 14, y + 81, 176, 22, item->owner, &lv_font_montserrat_16, PW_BLACK);
        }
        if (day->overflow) {
            char more[80];
            snprintf(more, sizeof more, "+ %u more - check phone", day->overflow);
            text(root, x, 1047, 195, 24, more, &lv_font_montserrat_14, PW_BLACK);
        }
    }
    block(root, 48, 1085, 1500, 2, PW_BLACK);
    text(root, 48, 1106, 1500, 34, view->footer, &lv_font_montserrat_24, PW_BLACK);
    block(root, 48, 1155, 10, 10, view->stale ? PW_RED : PW_GREEN);
    text(root, 73, 1147, 1475, 31, view->status, &lv_font_montserrat_16, PW_BLACK);
    lv_obj_invalidate(root);
}

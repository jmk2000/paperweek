#include "canvas.h"
#include "calendar_ui.h"
#include "lvgl.h"
static bool palette;
static lv_obj_t *root;
static lv_color_t ink(pw_colour c) {return lv_color_hex(pw_palette_rgb(c,palette));}
static const lv_font_t *font(int size) {
    switch(size) {
        case 14:return &lv_font_montserrat_14;
        case 16:return &lv_font_montserrat_16;
        case 20:return &lv_font_montserrat_20;
        case 24:return &lv_font_montserrat_24;
        case 32:return &lv_font_montserrat_32;
        case 40:return &lv_font_montserrat_40;
        case 48:return &lv_font_montserrat_48;
        default:return &lv_font_montserrat_20;
    }
}
void pw_draw_begin(bool paper) {
    palette=paper; root=lv_screen_active(); lv_obj_clean(root); lv_obj_remove_style_all(root);
    lv_obj_set_pos(root,0,0); lv_obj_set_size(root,PW_WIDTH,PW_HEIGHT);
    lv_obj_remove_flag(root,LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_bg_color(root,ink(PW_WHITE),0); lv_obj_set_style_bg_opa(root,LV_OPA_COVER,0);
}
void pw_draw_rect(int x,int y,int w,int h,pw_colour c) {
    lv_obj_t *obj=lv_obj_create(root); lv_obj_remove_style_all(obj);
    lv_obj_remove_flag(obj,LV_OBJ_FLAG_SCROLLABLE|LV_OBJ_FLAG_CLICKABLE);
    lv_obj_set_pos(obj,x,y); lv_obj_set_size(obj,w,h);
    lv_obj_set_style_bg_color(obj,ink(c),0); lv_obj_set_style_bg_opa(obj,LV_OPA_COVER,0);
}
void pw_draw_text(int x,int y,int w,int h,const char *value,int size,pw_colour c,int align) {
    lv_obj_t *obj=lv_label_create(root); lv_obj_remove_style_all(obj);
    lv_obj_set_pos(obj,x,y); lv_obj_set_size(obj,w,h);
    lv_obj_set_style_text_font(obj,font(size),0); lv_obj_set_style_text_color(obj,ink(c),0);
    lv_obj_set_style_text_line_space(obj,3,0);
    lv_obj_set_style_text_align(obj,align==1?LV_TEXT_ALIGN_CENTER:align==2?LV_TEXT_ALIGN_RIGHT:LV_TEXT_ALIGN_LEFT,0);
    lv_label_set_long_mode(obj,LV_LABEL_LONG_MODE_DOTS); lv_label_set_text(obj,value);
}
void pw_draw_end(void) {lv_obj_invalidate(root);}

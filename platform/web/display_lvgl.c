/* Real LVGL -> browser framebuffer. No SDL dependency in the web build.
 * The ESP32 port replaces this file, not ui/calendar_ui.c or core/calendar.c. */
#include "lvgl.h"
#include "view_model.h"
#include <emscripten.h>
#include <stdint.h>
static uint8_t draw_buffer[PW_WIDTH * 60 * 4] __attribute__((aligned(4)));
EM_JS(void, paint_pixels, (int x,int y,int width,int height,const uint8_t *bytes), {
    globalThis.PaperweekPaint.pixels(x,y,width,height,HEAPU8.subarray(bytes,bytes+width*height*4));
});
static void flush(lv_display_t *display,const lv_area_t *area,uint8_t *pixels){
    paint_pixels(area->x1,area->y1,lv_area_get_width(area),lv_area_get_height(area),pixels);
    lv_display_flush_ready(display);
}
static uint32_t tick(void){return (uint32_t)emscripten_get_now();}
void pw_platform_init(void){
    lv_init();lv_tick_set_cb(tick);
    lv_display_t *display=lv_display_create(PW_WIDTH,PW_HEIGHT);
    lv_display_set_color_format(display,LV_COLOR_FORMAT_XRGB8888);
    lv_display_set_buffers(display,draw_buffer,NULL,sizeof draw_buffer,LV_DISPLAY_RENDER_MODE_PARTIAL);
    lv_display_set_flush_cb(display,flush);
}
void pw_platform_resize(int height){lv_display_set_resolution(lv_display_get_default(),PW_WIDTH,height);}
void pw_platform_present(void){lv_timer_handler();lv_refr_now(NULL);}

#ifndef PAPERWEEK_VIEW_MODEL_H
#define PAPERWEEK_VIEW_MODEL_H
#include <stdbool.h>
#include <stdint.h>
/* Pure C view model: intentionally independent of SDL, Google, and the host OS. */
#define PW_WIDTH 1600
#define PW_HEIGHT 1200
#define PW_DAYS 7
#define PW_MAX_ITEMS 6
#define PW_MAX_CALENDARS 6
typedef enum { PW_BLACK, PW_WHITE, PW_RED, PW_YELLOW, PW_BLUE, PW_GREEN } pw_colour;
typedef struct { char name[48]; pw_colour colour; } pw_calendar;
typedef struct {
    char time[32], title[192], owner[48];
    pw_colour colour;
    bool all_day;
} pw_item;
typedef struct {
    char dow[8], number[4], month[8];
    bool today;
    unsigned count, overflow;
    pw_item items[PW_MAX_ITEMS];
} pw_day;
typedef struct {
    char title[96], month[96], span[96], week_number[24], today[96], timezone[64], mode[16];
    unsigned calendar_count;
    pw_calendar calendars[PW_MAX_CALENDARS];
    pw_day days[PW_DAYS];
    char footer[256], status[256];
    bool stale;
} pw_view;
#endif

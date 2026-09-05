#ifndef PAPERWEEK_VIEW_MODEL_H
#define PAPERWEEK_VIEW_MODEL_H
#include <stdbool.h>
#include <stdint.h>
/* Shared bounded view data: no SDL, Google, host OS, or heap ownership. */
#define PW_WIDTH 1600
#define PW_HEIGHT 1200
#define PW_DAYS 42
#define PW_MAX_ITEMS 6
#define PW_MAX_CALENDARS 6
typedef enum { PW_BLACK, PW_WHITE, PW_RED, PW_YELLOW, PW_BLUE, PW_GREEN } pw_colour;
typedef enum { PW_ROTA_UNKNOWN, PW_ROTA_OFF, PW_ROTA_WORK, PW_ROTA_ONCALL, PW_ROTA_CONFLICT } pw_rota;
typedef struct { char name[48], badge[4]; pw_colour colour; } pw_calendar;
typedef struct {
    char time[32], title[192], owner[48], badge[4];
    pw_colour colour;
    bool all_day;
} pw_item;
typedef struct {
    char dow[8], number[4], month[8];
    bool today, in_month;
    pw_rota rota;
    char rota_detail[48];
    unsigned count, overflow;
    pw_item items[PW_MAX_ITEMS];
} pw_day;
typedef struct {
    char title[96], month[96], span[160], week_number[24], today[96], timezone[64], mode[16];
    unsigned calendar_count, day_count, rows;
    bool is_month;
    char rota_owner[48];
    pw_colour rota_colour;
    pw_calendar calendars[PW_MAX_CALENDARS];
    pw_day days[PW_DAYS];
    char footer[256], status[256];
    bool stale;
} pw_view;
#endif

#ifndef PAPERWEEK_CALENDAR_H
#define PAPERWEEK_CALENDAR_H
#include "view_model.h"
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
#define PW_MAX_EVENTS 2048
/* Dates are civil-day ordinals since 1970-01-01 in the chosen display timezone.
 * The adapter expands recurrence and converts offsets/timezones. The core handles
 * day overlap, exclusive ends, rota rules, sorting, density, and navigation. */
typedef enum { PW_EVENT, PW_WORK, PW_ONCALL, PW_OFF } pw_event_kind;
typedef struct {
    char key[160], title[192];
    int calendar, start_day, end_day, start_second, end_second;
    double sort_time;
    bool all_day;
    pw_event_kind kind;
} pw_event;
typedef struct {
    char title[96], timezone[64];
    pw_calendar calendars[PW_MAX_CALENDARS];
    unsigned calendar_count;
    int rota_calendar; /* -1 disables rota. One tracked calendar in v0.3. */
    int week_start; /* 0 Sunday, 1 Monday */
    bool deduplicate;
} pw_config;
typedef struct {
    bool persistent, open;
    uint32_t until;
} pw_controls;
void pw_defaults(pw_config *config);
int pw_day_number(int year, unsigned month, unsigned day);
void pw_date_parts(int day, int *year, unsigned *month, unsigned *date);
int pw_weekday(int day); /* Sunday=0 */
int pw_month_length(int year, unsigned month);
int pw_move(int anchor, bool month, int delta);
void pw_range(int anchor, bool month, int week_start, int *first, unsigned *count);
bool pw_overlaps(const pw_event *event, int day);
/* Returns false for an invalid or over-capacity input; never truncates silently. */
bool pw_build_view(pw_view *view, const pw_config *config, const pw_event *events,
    unsigned count, int anchor, bool month, int today, int now_second,
    const char *mode, const char *status, bool stale);
void pw_controls_init(pw_controls *c, bool persistent);
/* 0 ignore, 1 reveal, 2 act. Until is armed after the render finishes. */
int pw_controls_press(pw_controls *c, uint32_t now, bool busy, uint32_t timeout_ms);
void pw_controls_visible(pw_controls *c, uint32_t now, uint32_t timeout_ms);
bool pw_controls_expire(pw_controls *c, uint32_t now, bool busy);
#ifdef __cplusplus
}
#endif
#endif

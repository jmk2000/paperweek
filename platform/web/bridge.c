#include "calendar.h"
#include "calendar_ui.h"
#include <string.h>

void pw_platform_init(void);
void pw_platform_present(void);
void pw_platform_resize(int height,int width);
void pw_viewport(int height,int width){if(width<1)width=1600;pw_ui_web_size(height,width);pw_platform_resize(height,width);}
static pw_config config;
static pw_event events[PW_MAX_EVENTS];
static unsigned event_count;
static pw_view view;
static pw_controls help;
static int anchor, today, now_second;
static bool month;
static char input[4096];
static unsigned timeout_ms=20000;
static void copy(char *to,unsigned cap,const char *from){unsigned i=0;if(from)for(;i+1<cap&&from[i];++i)to[i]=from[i];to[i]=0;}
char *pw_input_buffer(void){return input;}
unsigned pw_input_capacity(void){return sizeof input;}
void pw_init(void){pw_defaults(&config);pw_controls_init(&help,true);event_count=0;pw_platform_init();}
void pw_configure(const char *title,const char *timezone,int week_start,int rota,int deduplicate){
    pw_defaults(&config);copy(config.title,sizeof config.title,title);copy(config.timezone,sizeof config.timezone,timezone);
    config.week_start=week_start;config.rota_calendar=rota;config.deduplicate=deduplicate!=0;
}
int pw_person(int index,const char *label,const char *badge,int colour){
    if(index<0||index>=PW_MAX_CALENDARS||colour<0||colour>PW_GREEN||colour==PW_WHITE)return 0;
    copy(config.calendars[index].name,sizeof config.calendars[index].name,label);
    copy(config.calendars[index].badge,sizeof config.calendars[index].badge,badge);
    config.calendars[index].colour=(pw_colour)colour;
    if((unsigned)index>=config.calendar_count)config.calendar_count=(unsigned)index+1;
    return 1;
}
void pw_clear_events(void){event_count=0;}
int pw_add_event(const char *key,const char *title,int calendar,int start_day,int end_day,
    int start_second,int end_second,int all_day,int kind,double sort_time){
    if(event_count>=PW_MAX_EVENTS||calendar<0||calendar>=PW_MAX_CALENDARS||kind<PW_EVENT||kind>PW_OFF)return 0;
    pw_event *e=&events[event_count++];memset(e,0,sizeof *e);
    copy(e->key,sizeof e->key,key);copy(e->title,sizeof e->title,title);
    e->calendar=calendar;e->start_day=start_day;e->end_day=end_day;e->start_second=start_second;e->end_second=end_second;
    e->all_day=all_day!=0;e->kind=(pw_event_kind)kind;e->sort_time=sort_time;return 1;
}
void pw_select(int day,int is_month){anchor=day;month=is_month!=0;}
void pw_clock(int day,int second){today=day;now_second=second;}
int pw_anchor(void){return anchor;}
int pw_is_month(void){return month;}
int pw_first(void){int first;unsigned count;pw_range(anchor,month,config.week_start,&first,&count);return first;}
int pw_day_count(void){int first;unsigned count;pw_range(anchor,month,config.week_start,&first,&count);return (int)count;}
void pw_navigate(int button){
    if(button==0)anchor=pw_move(anchor,month,-1);
    else if(button==1)anchor=today;
    else if(button==2)month=!month;
    else if(button==3)anchor=pw_move(anchor,month,1);
}
void pw_help_configure(int persistent,int seconds){
    pw_controls_init(&help,persistent!=0);timeout_ms=(unsigned)(seconds<5?5:seconds>120?120:seconds)*1000;
}
int pw_press(unsigned now,int busy){return pw_controls_press(&help,now,busy!=0,timeout_ms);}
void pw_visible(unsigned now){pw_controls_visible(&help,now,timeout_ms);}
int pw_expire(unsigned now,int busy){return pw_controls_expire(&help,now,busy!=0);}
int pw_help_open(void){return help.open;}
unsigned pw_prepare(const char *mode,const char *status,int stale){
    if(!pw_build_view(&view,&config,events,event_count,anchor,month,today,now_second,mode,status,stale!=0))return 0;
    const unsigned char *bytes=(const unsigned char *)&view;unsigned hash=2166136261U;
    for(unsigned i=0;i<sizeof view;++i)hash=(hash^bytes[i])*16777619U;
    return hash?hash:1;
}
void pw_draw(int paper){pw_ui_render_ex(&view,paper!=0,help.open,help.persistent);pw_platform_present();}
int pw_render(int paper,const char *mode,const char *status,int stale){
    if(!pw_prepare(mode,status,stale))return 0;pw_draw(paper);return 1;
}
void pw_placeholder(int paper){pw_ui_refresh_placeholder(paper!=0);pw_platform_present();}
int pw_day_rota(int day){return day>=0&&day<(int)view.day_count?(int)view.days[day].rota:-1;}
int pw_day_items(int day){return day>=0&&day<(int)view.day_count?(int)view.days[day].count:-1;}
int pw_day_overflow(int day){return day>=0&&day<(int)view.day_count?(int)view.days[day].overflow:-1;}
unsigned pw_events_count(void){return event_count;}

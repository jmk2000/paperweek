#include "calendar.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks;
#define CHECK(x) do{++checks;if(!(x)){fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
static pw_view view;
static pw_event events[PW_MAX_EVENTS];
static pw_config config;
static void setup(void){pw_defaults(&config);config.calendar_count=4;const char *names[]={"Adult 1","Adult 2","Child 1","Child 2"};pw_colour colours[]={PW_BLUE,PW_GREEN,PW_RED,PW_YELLOW};for(unsigned i=0;i<4;++i){snprintf(config.calendars[i].name,48,"%s",names[i]);snprintf(config.calendars[i].badge,4,"%u",i+1);config.calendars[i].colour=colours[i];}config.rota_calendar=1;memset(events,0,sizeof events);}
static pw_event make(int cal,int day,int start,int duration,pw_event_kind kind){pw_event e={0};e.calendar=cal;e.start_day=day;e.end_day=day+(start+duration)/86400;e.start_second=start;e.end_second=(start+duration)%86400;e.kind=kind;e.sort_time=(double)day*86400000+start*1000;snprintf(e.key,sizeof e.key,"%d-%d-%d-%d",cal,day,start,kind);snprintf(e.title,sizeof e.title,"Appointment");return e;}
static bool build(unsigned count,int day,bool month){return pw_build_view(&view,&config,events,count,day,month,day,0,"demo","DEMO",false);}
int main(void){
    CHECK(pw_day_number(1970,1,1)==0);CHECK(pw_weekday(0)==4);CHECK(pw_weekday(-1)==3);
    CHECK(pw_month_length(2000,2)==29);CHECK(pw_month_length(2100,2)==28);CHECK(pw_month_length(2024,2)==29);
    for(int y=1900;y<=2200;y+=3)for(unsigned m=1;m<=12;++m){int yr;unsigned mo,d;int day=pw_day_number(y,m,(unsigned)pw_month_length(y,m));pw_date_parts(day,&yr,&mo,&d);CHECK(yr==y&&mo==m&&d==(unsigned)pw_month_length(y,m));}
    int first;unsigned count;
    pw_range(pw_day_number(2021,2,5),true,1,&first,&count);CHECK(count==28);CHECK(first==pw_day_number(2021,2,1));
    pw_range(pw_day_number(2026,8,1),true,1,&first,&count);CHECK(count==42);
    pw_range(pw_day_number(2026,10,1),true,1,&first,&count);CHECK(count==35);
    pw_range(pw_day_number(2026,10,1),true,0,&first,&count);CHECK(pw_weekday(first)==0);
    CHECK(pw_move(pw_day_number(2026,1,31),true,1)==pw_day_number(2026,2,28));
    CHECK(pw_move(pw_day_number(2024,1,31),true,1)==pw_day_number(2024,2,29));
    CHECK(pw_move(pw_day_number(2026,1,1),true,-1)==pw_day_number(2025,12,1));
    int day=pw_day_number(2026,10,5);setup();CHECK(build(0,day,false));CHECK(view.rows==1&&view.day_count==7);CHECK(view.days[0].rota==PW_ROTA_UNKNOWN);
    events[0]=make(1,day,8*3600,9*3600,PW_ONCALL);CHECK(build(1,day,false));CHECK(view.days[0].rota==PW_ROTA_ONCALL);CHECK(view.days[0].count==0);
    events[1]=make(1,day,0,86400,PW_OFF);events[1].all_day=true;CHECK(build(2,day,false));CHECK(view.days[0].rota==PW_ROTA_CONFLICT);CHECK(strstr(view.footer,"CHECK ROTA")!=NULL);
    CHECK(build(1,day+5,false)); /* weekend is not automatically off */
    events[0]=make(1,day+5,20*3600,12*3600,PW_WORK);CHECK(build(1,day,false));CHECK(view.days[5].rota==PW_ROTA_WORK);CHECK(view.days[6].rota==PW_ROTA_WORK);
    events[0]=make(0,day,23*3600,3600,PW_EVENT);CHECK(pw_overlaps(&events[0],day));CHECK(!pw_overlaps(&events[0],day+1));
    events[0]=make(0,day,23*3600,7200,PW_EVENT);CHECK(pw_overlaps(&events[0],day+1));
    events[0]=make(0,day,0,86400,PW_EVENT);events[0].all_day=true;CHECK(!pw_overlaps(&events[0],day+1));
    events[0]=make(0,day,10*3600,0,PW_EVENT);CHECK(pw_overlaps(&events[0],day));
    /* Local end clock before start during DST fall-back: adapter validates actual instants. */
    events[0]=make(0,day,5400,600,PW_EVENT);events[0].end_second=4200;CHECK(build(1,day,false));
    for(unsigned i=0;i<9;++i)events[i]=make(0,day,(18-(int)i)*3600,1800,PW_EVENT);
    CHECK(build(9,day,false));CHECK(view.days[0].count==6);CHECK(view.days[0].overflow==3);CHECK(strcmp(view.days[0].items[0].time,"10:00")==0);
    events[0].all_day=true;events[0].end_day=day+1;CHECK(build(9,day,false));CHECK(view.days[0].items[0].all_day);
    setup();events[0]=make(0,day,36000,3600,PW_EVENT);events[1]=events[0];events[1].calendar=2;
    CHECK(build(2,day,false));CHECK(view.days[0].count==2);config.deduplicate=true;CHECK(build(2,day,false));CHECK(view.days[0].count==1);
    CHECK(strcmp(view.days[0].items[0].badge,"1")==0);
    config.rota_calendar=-1;events[0]=make(1,day,36000,3600,PW_WORK);CHECK(build(1,day,false));CHECK(view.days[0].count==1);CHECK(view.rota_owner[0]==0);
    config.calendar_count=7;CHECK(!build(0,day,false));config.calendar_count=0;CHECK(!build(0,day,false));setup();
    events[0]=make(1,day,36000,3600,PW_OFF);CHECK(!build(1,day,false));
    events[0]=make(4,day,36000,3600,PW_EVENT);CHECK(!build(1,day,false));
    CHECK(!build(PW_MAX_EVENTS+1,day,false));
    pw_controls c;pw_controls_init(&c,false);CHECK(pw_controls_press(&c,100,false,20000)==1);CHECK(c.open);CHECK(c.until==0);
    CHECK(!pw_controls_expire(&c,20100,true));pw_controls_visible(&c,19100,20000);CHECK(!pw_controls_expire(&c,39099,false));CHECK(pw_controls_expire(&c,39100,false));
    CHECK(pw_controls_press(&c,40000,true,20000)==0);CHECK(!c.open);CHECK(pw_controls_press(&c,40000,false,20000)==1);CHECK(pw_controls_press(&c,40001,false,20000)==2);
    pw_controls_init(&c,true);CHECK(pw_controls_press(&c,0,false,20000)==2);CHECK(!c.open);
    pw_controls_init(&c,false);pw_controls_press(&c,0xfffffff0U,false,20000);pw_controls_visible(&c,0xfffffff0U,20000);CHECK(!pw_controls_expire(&c,10,false));CHECK(pw_controls_expire(&c,20000,false));
    printf("%u calendar/core checks passed\n",checks);return 0;
}

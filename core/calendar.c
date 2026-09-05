#include "calendar.h"
#include <stdio.h>
#include <string.h>

static const char *weekdays[] = {"SUN","MON","TUE","WED","THU","FRI","SAT"};
static const char *months[] = {"January","February","March","April","May","June","July","August","September","October","November","December"};
static const char *shortmonths[] = {"JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"};
static void copy(char *to, size_t cap, const char *from) {
    if(!cap) return;
    size_t i=0; if(from) for(; i+1<cap && from[i]; ++i) to[i]=from[i]; to[i]=0;
}
static int mod(int a,int n) { int r=a%n;return r<0?r+n:r; }
/* Gregorian civil-date conversion, independent of time_t and host timezone.
 * Days are measured from the civil date 1970-01-01, not 24-hour durations. */
int pw_day_number(int y,unsigned m,unsigned d) {
    y -= m<=2;
    int era=(y>=0?y:y-399)/400;
    unsigned yo=(unsigned)(y-era*400);
    unsigned mp=m>2?m-3:m+9;
    unsigned doy=(153*mp+2)/5+d-1;
    unsigned doe=yo*365+yo/4-yo/100+doy;
    return era*146097+(int)doe-719468;
}
void pw_date_parts(int z,int *year,unsigned *month,unsigned *date) {
    z+=719468;
    int era=(z>=0?z:z-146096)/146097;
    unsigned doe=(unsigned)(z-era*146097);
    unsigned yo=(doe-doe/1460+doe/36524-doe/146096)/365;
    int y=(int)yo+era*400;
    unsigned doy=doe-(365*yo+yo/4-yo/100);
    unsigned mp=(5*doy+2)/153;
    *date=doy-(153*mp+2)/5+1;
    *month=mp<10?mp+3:mp-9;
    *year=y+(*month<=2);
}
int pw_weekday(int day) {return mod(day+4,7);}
int pw_month_length(int y,unsigned m) {
    static const int lengths[]={31,28,31,30,31,30,31,31,30,31,30,31};
    if(m<1||m>12)return 0;
    return lengths[m-1]+(m==2 && y%4==0 && (y%100!=0||y%400==0));
}
int pw_move(int anchor,bool month,int delta) {
    if(!month) return anchor+7*delta;
    int y;unsigned m,d;pw_date_parts(anchor,&y,&m,&d);
    int total=y*12+(int)m-1+delta;
    int nm=mod(total,12); y=(total-nm)/12; m=(unsigned)nm+1;
    int length=pw_month_length(y,m);if((int)d>length)d=(unsigned)length;
    return pw_day_number(y,m,d);
}
void pw_range(int anchor,bool month,int week_start,int *first,unsigned *count) {
    int start=anchor;
    if(month) {int y;unsigned m,d;pw_date_parts(anchor,&y,&m,&d);start=pw_day_number(y,m,1);}
    *first=start-mod(pw_weekday(start)-week_start,7);
    if(!month) {*count=7;return;}
    int y;unsigned m,d;pw_date_parts(anchor,&y,&m,&d);
    int last=pw_day_number(y,m,(unsigned)pw_month_length(y,m));
    *count=(unsigned)((last-*first)/7+1)*7;
}
void pw_defaults(pw_config *c) {
    memset(c,0,sizeof *c);copy(c->title,sizeof c->title,"Our calendar");
    copy(c->timezone,sizeof c->timezone,"UTC");c->rota_calendar=-1;c->week_start=1;
}
bool pw_overlaps(const pw_event *e,int day) {
    if(e->all_day)return e->start_day<=day && day<e->end_day;
    if(e->start_day==e->end_day && e->start_second==e->end_second)return e->start_day==day;
    return e->start_day<=day && (e->end_day>day || (e->end_day==day && e->end_second>0));
}
static void event_time(const pw_event *e,int day,char *out,size_t cap) {
    if(e->all_day)copy(out,cap,"ALL DAY");
    else if(e->start_day<day) {
        if(e->end_day==day)snprintf(out,cap,"Until %02d:%02d",e->end_second/3600,e->end_second/60%60);
        else copy(out,cap,"Continues");
    } else snprintf(out,cap,"%02d:%02d%s",e->start_second/3600,e->start_second/60%60,
        e->end_day>day && (e->end_day>day+1 || e->end_second>0)?" >":"");
}
static void rota(const pw_event *events,unsigned count,int cal,int day,pw_day *out) {
    bool work=false,call=false,off=false;unsigned timed=0;char last[48]="";
    for(unsigned i=0;i<count;++i) {
        const pw_event *e=&events[i];
        if(e->calendar!=cal || e->kind==PW_EVENT || !pw_overlaps(e,day))continue;
        if(e->kind==PW_OFF)off=true;
        if(e->kind==PW_WORK || e->kind==PW_ONCALL) {
            work=true; if(e->kind==PW_ONCALL)call=true;
            if(!e->all_day) {
                char current[48];
                if(e->start_day<day) {
                    if(e->end_day==day)snprintf(current,sizeof current,"Until %02d:%02d",e->end_second/3600,e->end_second/60%60);
                    else copy(current,sizeof current,"Overnight");
                } else if(e->end_day>day)snprintf(current,sizeof current,"%02d:%02d >",e->start_second/3600,e->start_second/60%60);
                else snprintf(current,sizeof current,"%02d:%02d-%02d:%02d",e->start_second/3600,e->start_second/60%60,e->end_second/3600,e->end_second/60%60);
                if(strcmp(last,current)!=0){++timed;copy(last,sizeof last,current);}
            }
        }
    }
    if(work&&off){out->rota=PW_ROTA_CONFLICT;copy(out->rota_detail,sizeof out->rota_detail,"CHECK ROTA");}
    else if(work){out->rota=call?PW_ROTA_ONCALL:PW_ROTA_WORK;copy(out->rota_detail,sizeof out->rota_detail,timed>1?"Multiple shift times":last);}
    else if(off){out->rota=PW_ROTA_OFF;copy(out->rota_detail,sizeof out->rota_detail,"Not working");}
    else {out->rota=PW_ROTA_UNKNOWN;copy(out->rota_detail,sizeof out->rota_detail,"Not entered");}
}
static bool earlier(const pw_event *a,const pw_event *b) {
    if(a->all_day!=b->all_day)return a->all_day;
    if(a->sort_time!=b->sort_time)return a->sort_time<b->sort_time;
    int title=strcmp(a->title,b->title);
    if(title!=0)return title<0;
    return a->calendar<b->calendar;
}
static bool valid_event(const pw_event *e,unsigned calendars) {
    if(e->calendar<0||(unsigned)e->calendar>=calendars)return false;
    if(e->kind<PW_EVENT||e->kind>PW_OFF)return false;
    if(e->start_day<-25567||e->end_day>84370||e->end_day<e->start_day)return false;
    if(e->start_second<0||e->start_second>86399||e->end_second<0||e->end_second>86399)return false;
    if(e->kind==PW_OFF&&!e->all_day)return false;
    /* Folded clock times during DST fall-back can have end wall-time < start wall-time.
       The adapter validates the actual instants before converting to civil fields. */
    if(e->all_day&&e->end_day<=e->start_day)return false;
    return true;
}
bool pw_build_view(pw_view *v,const pw_config *c,const pw_event *events,unsigned count,
    int anchor,bool month,int today,int now_second,const char *mode,const char *status,bool stale) {
    if(!v||!c||(count&&!events)||count>PW_MAX_EVENTS||c->calendar_count<1||c->calendar_count>PW_MAX_CALENDARS)return false;
    if(c->week_start!=0&&c->week_start!=1)return false;
    if(c->rota_calendar < -1 || c->rota_calendar >= (int)c->calendar_count)return false;
    if(anchor<-25567||anchor>84370||now_second<0||now_second>86399)return false;
    for(unsigned i=0;i<count;++i)if(!valid_event(&events[i],c->calendar_count))return false;
    memset(v,0,sizeof *v);v->is_month=month;v->calendar_count=c->calendar_count;
    memcpy(v->calendars,c->calendars,sizeof v->calendars);
    copy(v->title,sizeof v->title,c->title);copy(v->timezone,sizeof v->timezone,c->timezone);
    copy(v->mode,sizeof v->mode,mode);copy(v->status,sizeof v->status,status);v->stale=stale;
    if(c->rota_calendar>=0){copy(v->rota_owner,sizeof v->rota_owner,c->calendars[c->rota_calendar].name);v->rota_colour=c->calendars[c->rota_calendar].colour;}
    int first;unsigned days;pw_range(anchor,month,c->week_start,&first,&days);
    v->day_count=days;v->rows=days/7;
    int ay,sy,ey,ty;unsigned am,ad,sm,sd,em,ed,tm,td;
    pw_date_parts(anchor,&ay,&am,&ad);pw_date_parts(first,&sy,&sm,&sd);
    pw_date_parts(first+(int)days-1,&ey,&em,&ed);pw_date_parts(today,&ty,&tm,&td);
    if(month)snprintf(v->month,sizeof v->month,"%s %d",months[am-1],ay);
    else if(sm==em&&sy==ey)snprintf(v->month,sizeof v->month,"%s %d",months[sm-1],sy);
    else snprintf(v->month,sizeof v->month,"%s %d / %s %d",shortmonths[sm-1],sy,shortmonths[em-1],ey);
    if(month)snprintf(v->span,sizeof v->span,"%s / %s first / short titles; +n means more events",c->title,c->week_start?"Monday":"Sunday");
    else snprintf(v->span,sizeof v->span,"%u %s - %u %s / WEEK VIEW",sd,shortmonths[sm-1],ed,shortmonths[em-1]);
    snprintf(v->today,sizeof v->today,"%s / %u %s",weekdays[pw_weekday(today)],td,shortmonths[tm-1]);
    unsigned capacity=month?(v->rows==4?5:v->rows==5?4:3):PW_MAX_ITEMS;
    /* Stable, optional cross-calendar dedup: earliest configured calendar wins. */
    bool skip[PW_MAX_EVENTS];memset(skip,0,sizeof skip);
    for(unsigned i=0;i<count;++i) {
        if(events[i].kind!=PW_EVENT&&events[i].calendar==c->rota_calendar){skip[i]=true;continue;}
        if(!c->deduplicate||!events[i].key[0])continue;
        for(unsigned j=0;j<count;++j) {
            if(i==j || (events[j].kind!=PW_EVENT&&events[j].calendar==c->rota_calendar))continue;
            if((events[j].calendar<events[i].calendar || (events[j].calendar==events[i].calendar&&j<i)) && strcmp(events[j].key,events[i].key)==0){skip[i]=true;break;}
        }
    }
    unsigned conflicts=0;
    for(unsigned d=0;d<days;++d) {
        int day=first+(int)d;int y;unsigned m,num;pw_date_parts(day,&y,&m,&num);
        pw_day *out=&v->days[d];copy(out->dow,sizeof out->dow,weekdays[pw_weekday(day)]);
        snprintf(out->number,sizeof out->number,"%u",num);copy(out->month,sizeof out->month,shortmonths[m-1]);
        out->today=day==today;out->in_month=m==am&&y==ay;
        if(c->rota_calendar>=0)rota(events,count,c->rota_calendar,day,out);
        if(out->rota==PW_ROTA_CONFLICT)++conflicts;
        unsigned matches=0, selected[PW_MAX_ITEMS]={0}, kept=0;
        for(unsigned i=0;i<count;++i) {
            if(skip[i]||!pw_overlaps(&events[i],day))continue;
            ++matches;unsigned p=kept;
            while(p>0&&earlier(&events[i],&events[selected[p-1]]))--p;
            if(p>=capacity)continue;
            unsigned end=kept<capacity?kept:capacity-1;
            for(unsigned k=end;k>p;--k)selected[k]=selected[k-1];
            selected[p]=i;if(kept<capacity)++kept;
        }
        out->count=kept;out->overflow=matches-kept;
        for(unsigned i=0;i<kept;++i) {
            const pw_event *e=&events[selected[i]];const pw_calendar *cal=&c->calendars[e->calendar];pw_item *item=&out->items[i];
            event_time(e,day,item->time,sizeof item->time);copy(item->title,sizeof item->title,e->title);
            copy(item->owner,sizeof item->owner,cal->name);copy(item->badge,sizeof item->badge,cal->badge);
            item->colour=cal->colour;item->all_day=e->all_day;
        }
    }
    const pw_event *next=NULL;
    for(unsigned i=0;i<count;++i){const pw_event *e=&events[i];
        if(skip[i]||e->all_day||e->start_day<today||(e->start_day==today&&e->start_second<now_second))continue;
        if(!next||earlier(e,next))next=e;
    }
    if(conflicts)snprintf(v->footer,sizeof v->footer,"CHECK ROTA / Working and off-duty overlap on %u date(s).",conflicts);
    else if(next){int y;unsigned m,d;pw_date_parts(next->start_day,&y,&m,&d);
        /* Bounded temporaries keep native compiler checks and our small WASM
         * formatter in agreement: the latter deliberately has no %.Ns support. */
        char owner[33],title[151];
        copy(owner,sizeof owner,c->calendars[next->calendar].name);
        copy(title,sizeof title,next->title);
        snprintf(v->footer,sizeof v->footer,"NEXT IN LOADED RANGE / %s %u %s %02d:%02d / %s: %s",weekdays[pw_weekday(next->start_day)],d,shortmonths[m-1],next->start_second/3600,next->start_second/60%60,owner,title);
    } else copy(v->footer,sizeof v->footer,"No upcoming timed events in the loaded range.");
    return true;
}
void pw_controls_init(pw_controls *c,bool persistent){c->persistent=persistent;c->open=false;c->until=0;}
int pw_controls_press(pw_controls *c,uint32_t now,bool busy,uint32_t timeout_ms){
    if(busy)return 0;
    if(!c->persistent&&!c->open){c->open=true;c->until=0;return 1;}
    if(c->open)c->until=now+timeout_ms;
    return 2;
}
void pw_controls_visible(pw_controls *c,uint32_t now,uint32_t timeout_ms){if(c->open)c->until=now+timeout_ms;}
bool pw_controls_expire(pw_controls *c,uint32_t now,bool busy){
    if(!busy&&c->open&&c->until&&(int32_t)(now-c->until)>=0){c->open=false;c->until=0;return true;}return false;
}

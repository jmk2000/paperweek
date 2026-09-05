#include "calendar_ui.h"
#include "canvas.h"
#include <stdio.h>
#include <string.h>

static int web_height;
void pw_ui_web_height(int height) { web_height=height; }
static int grid_bottom(void) { return web_height ? web_height-90 : 1035; }

/* Representative colours only; not a calibrated Spectra 6 proof. */
uint32_t pw_palette_rgb(pw_colour c, bool paper) {
    static const uint32_t reflective[] = {0x20211e, 0xf5f3e9, 0xad332b, 0xd6b633, 0x365889, 0x3e704e};
    static const uint32_t clean[] = {0x111111, 0xffffff, 0xc93028, 0xeacb23, 0x285bbb, 0x27834b};
    unsigned i = (unsigned)c; if (i >= 6) i = PW_BLACK;
    return paper ? reflective[i] : clean[i];
}
static void rect(int x,int y,int w,int h,pw_colour c) { pw_draw_rect(x,y,w,h,c); }
static void txt(int x,int y,int w,int h,const char *t,int s,pw_colour c) { pw_draw_text(x,y,w,h,t,s,c,0); }
static void centred(int x,int y,int w,int h,const char *t,int s,pw_colour c) { pw_draw_text(x,y,w,h,t,s,c,1); }
static void right(int x,int y,int w,int h,const char *t,int s) { pw_draw_text(x,y,w,h,t,s,PW_BLACK,2); }
static void border(int x,int y,int w,int h,int t,pw_colour c) {
    rect(x,y,w,t,c); rect(x,y+h-t,w,t,c); rect(x,y,t,h,c); rect(x+w-t,y,t,h,c);
}
static const char *rota_text(pw_rota r) {
    switch(r) {
        case PW_ROTA_WORK: return "WORK";
        case PW_ROTA_ONCALL: return "WORK + CALL";
        case PW_ROTA_OFF: return "OFF";
        case PW_ROTA_CONFLICT: return "CHECK ROTA";
        default: return "? ROTA";
    }
}
static void shift(int x, int y, int w, const pw_day *d, const pw_view *v, bool compact) {
    int h = compact ? 24 : 55;
    bool work = d->rota == PW_ROTA_WORK || d->rota == PW_ROTA_ONCALL;
    pw_colour fg = work && v->rota_colour != PW_YELLOW ? PW_WHITE : PW_BLACK;
    if(work) rect(x,y,w,h,v->rota_colour);
    else border(x,y,w,h,d->rota == PW_ROTA_CONFLICT ? 3 : 1,d->rota == PW_ROTA_CONFLICT ? PW_RED : PW_BLACK);
    if(d->rota == PW_ROTA_ONCALL) { rect(x+w-26,y,26,h,PW_YELLOW); centred(x+w-26,y+(compact?3:17),26,24,"C",16,PW_BLACK); }
    int labelw = w - (d->rota == PW_ROTA_ONCALL ? 40 : 16);
    txt(x+8,y+(compact?3:6),labelw,23,(compact && d->rota==PW_ROTA_ONCALL)?"WORK":rota_text(d->rota),compact?14:16,fg);
    if(!compact) txt(x+8,y+30,labelw,22,d->rota_detail,14,fg);
}
static void rota_legend(const pw_view *v) {
    if(!v->rota_owner[0]) return;
    char name[90]; snprintf(name,sizeof name,"%s's rota",v->rota_owner);
    txt(44,224,242,24,name,16,PW_BLACK);
    rect(290,226,17,14,v->rota_colour); txt(316,221,135,26,"Working",16,PW_BLACK);
    rect(478,226,17,14,v->rota_colour); rect(489,226,6,14,PW_YELLOW);
    txt(505,221,206,26,"Working + on-call",16,PW_BLACK);
    border(733,226,17,14,1,PW_BLACK); txt(760,221,156,26,"Not working",16,PW_BLACK);
    txt(955,221,567,26,"? Not entered / C On-call / no weekday assumptions",14,PW_BLACK);
}
static void week_view(const pw_view *v) {
    for(int d=0; d<7; ++d) {
        const pw_day *day = &v->days[d]; int x=44+d*216;
        if(d) rect(x-10,275,1,grid_bottom()-275,PW_BLACK);
        txt(x,278,91,30,day->dow,20,PW_BLACK);
        txt(x+105,270,82,51,day->number,40,PW_BLACK);
        txt(x,310,92,23,day->month,14,PW_BLACK);
        if(day->today) { rect(x+97,320,95,5,PW_BLACK); }
        if(v->rota_owner[0]) shift(x,344,194,day,v,false);
        else rect(x,380,194,1,PW_BLACK);
        if(day->count==0) txt(x+3,429,187,65,strcmp(v->mode,"unavailable")==0 ? "Calendar not\nloaded yet" : "No events",20,PW_BLACK);
        for(unsigned i=0; i<day->count; ++i) {
            const pw_item *item=&day->items[i]; int y=421+(int)i*(web_height?(grid_bottom()-421-30)/6:96);
            rect(x,y+2,5,82,item->colour);
            txt(x+13,y,180,25,item->time,20,PW_BLACK);
            txt(x+13,y+26,180,52,item->title,20,PW_BLACK);
            txt(x+13,y+76,180,20,item->owner,14,PW_BLACK);
        }
        if(day->overflow) {
            char more[64]; snprintf(more,sizeof more,"+%u more on phone",day->overflow);
            txt(x,grid_bottom()-30,196,24,more,14,PW_BLACK);
        }
    }
}
static void compact_entry(int x, int y, int height, const pw_item *item) {
    char line[256], when[32];
    if(item->all_day) when[0]=0;
    else {
        snprintf(when,sizeof when,"%s",item->time);
        if(strlen(when)==5 && strcmp(when+2,":00")==0) when[2]=0;
        if(when[0]=='0' && when[1]>='0' && when[1]<='9') memmove(when,when+1,strlen(when));
    }
    snprintf(line,sizeof line,"%s%s%s",when,when[0]?" ":"",item->title);
    rect(x,y+2,18,18,item->colour);
    centred(x,y+2,18,19,item->badge,14,(item->colour==PW_YELLOW)?PW_BLACK:PW_WHITE);
    txt(x+25,y,170,height,line,height>23?20:16,PW_BLACK);
}
static void month_view(const pw_view *v) {
    for(int d=0; d<7; ++d) txt(52+d*216,273,190,28,v->days[d].dow,16,PW_BLACK);
    int top=309, height=(grid_bottom()-309)/(int)v->rows;
    for(unsigned i=0; i<v->day_count; ++i) {
        int x=44+(int)(i%7)*216, y=top+(int)(i/7)*height;
        const pw_day *day=&v->days[i];
        rect(x,y,216,1,PW_BLACK);
        if(i%7) rect(x-8,y,1,height,PW_BLACK);
        if(day->today) { rect(x+1,y+7,38,31,PW_BLACK); centred(x+1,y+8,38,31,day->number,24,PW_WHITE); }
        else txt(x+4,y+8,48,32,day->number,24,PW_BLACK);
        if(!day->in_month) txt(x+43,y+13,33,23,day->month,14,PW_BLACK);
        if(v->rota_owner[0]) shift(x+82,y+10,116,day,v,true);
        int step=web_height && height>=240?46:21;
        for(unsigned n=0; n<day->count; ++n) compact_entry(x+4,y+40+(int)n*step,step>21?43:23,&day->items[n]);
        if(day->overflow) {
            char more[32]; snprintf(more,sizeof more,"+%u more",day->overflow);
            txt(x+4,y+height-18,191,18,more,14,PW_BLACK);
        }
    }
}
static void controls(const pw_view *v, bool overlay, bool persistent) {
    static const char *actions[]={"PREVIOUS","TODAY", "", "NEXT"};
    if(!overlay && !persistent) {
        centred(44,1148,1512,28,"Press any frame button for help / first press only reveals labels",16,PW_BLACK);
        return;
    }
    int top=overlay?1039:1126;
    if(overlay) {
        rect(24,top,1552,161,PW_WHITE); border(24,top,1552,161,3,PW_BLACK);
        centred(44,1052,1512,31,"FRAME BUTTONS / press again to act / help closes after the configured timeout",20,PW_BLACK);
        centred(44,1090,1512,23,"These pointers assume four equally spaced buttons along the bottom edge.",14,PW_BLACK);
    } else rect(44,1126,1512,1,PW_BLACK);
    for(int i=0;i<4;++i) {
        int x=44+i*378, centre=x+189; char label[70];
        snprintf(label,sizeof label,"%d  %s",i+1,i==2?(v->is_month?"WEEK VIEW":"MONTH VIEW"):actions[i]);
        centred(x,1137,378,30,label,20,PW_BLACK);
        rect(centre-1,1172,2,18,PW_BLACK);
        rect(centre-6,1184,12,2,PW_BLACK); rect(centre-4,1187,8,2,PW_BLACK); rect(centre-2,1190,4,2,PW_BLACK);
    }
}
void pw_ui_render_ex(const pw_view *v,bool paper,bool overlay,bool persistent) {
    pw_draw_begin(paper);
    txt(44,29,1100,25,"P A P E R W E E K  /  SHARED CALENDAR",16,PW_BLACK);
    txt(41,72,1035,65,v->is_month?v->month:v->title,48,PW_BLACK);
    right(1000,83,553,40,v->is_month?"AT A GLANCE":v->month,24);
    txt(44,145,1090,30,v->span,v->is_month?16:20,PW_BLACK);
    right(1090,145,463,30,v->today,16);
    int legend_width=v->calendar_count?1512/(int)v->calendar_count:378;
    for(unsigned i=0;i<v->calendar_count;++i) {
        int x=44+(int)i*legend_width;
        rect(x,184,25,25,v->calendars[i].colour);
        centred(x,186,25,24,v->calendars[i].badge,16,v->calendars[i].colour==PW_YELLOW?PW_BLACK:PW_WHITE);
        txt(x+38,184,legend_width-50,30,v->calendars[i].name,20,PW_BLACK);
    }
    rota_legend(v); rect(44,257,1512,2,PW_BLACK);
    if(v->is_month) month_view(v); else week_view(v);
    int footer=grid_bottom()+11;
    rect(44,footer,1512,2,PW_BLACK);
    txt(44,footer+18,1512,33,v->footer,20,PW_BLACK);
    rect(44,footer+57,8,8,v->stale?PW_RED:PW_GREEN);
    txt(63,footer+52,1489,23,v->status,14,PW_BLACK);
    if(!web_height) controls(v,overlay,persistent); pw_draw_end();
}
void pw_ui_render(const pw_view *v,bool paper) { pw_ui_render_ex(v,paper,false,true); }
void pw_ui_refresh_placeholder(bool paper) {
    pw_draw_begin(paper);
    centred(130,490,1340,50,"SCREEN UNAVAILABLE DURING REFRESH",32,PW_BLACK);
    centred(130,558,1340,35,"Timing demonstration only - real pigment movement and flashing are not simulated.",20,PW_BLACK);
    centred(130,613,1340,35,"This explanatory message would not appear on the real panel.",20,PW_BLACK);
    pw_draw_end();
}

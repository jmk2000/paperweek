/* Desktop-only SDL adapter. calendar_ui.c is the reusable LVGL renderer. */
#include "calendar_ui.h"
#include "view_reader.hpp"
#include "lvgl.h"
#include <SDL.h>
#include <algorithm>
#include <chrono>
#include <climits>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include <sys/stat.h>

namespace {
std::vector<uint32_t> draw_pixels(PW_WIDTH * PW_HEIGHT), visible_pixels(PW_WIDTH * PW_HEIGHT);
SDL_Window* window = nullptr;
SDL_Renderer* renderer = nullptr;
SDL_Texture* texture = nullptr;
bool paper = true, dirty = false;
const auto started = std::chrono::steady_clock::now();
uint32_t ticks() {
    return static_cast<uint32_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - started).count());
}
uint32_t quantise(uint32_t pixel) {
    int r = (pixel >> 16) & 255, g = (pixel >> 8) & 255, b = pixel & 255;
    int best = INT_MAX;
    uint32_t result = 0;
    // Prevent grey antialiasing on black text becoming a coloured fringe.
    bool neutral = std::max({r, g, b}) - std::min({r, g, b}) < 20;
    for (int i = 0; i < 6; ++i) {
        if (neutral && i > PW_WHITE) continue;
        uint32_t p = pw_palette_rgb(static_cast<pw_colour>(i), paper);
        int dr = r - static_cast<int>((p >> 16) & 255);
        int dg = g - static_cast<int>((p >> 8) & 255);
        int db = b - static_cast<int>(p & 255);
        int distance = dr * dr + dg * dg + db * db;
        if (distance < best) { best = distance; result = p; }
    }
    return 0xff000000U | result;
}
void flush(lv_display_t* display, const lv_area_t* area, uint8_t* pixels) {
    // FULL render mode always supplies the complete 1600x1200 framebuffer.
    (void)area;
    const auto* source = reinterpret_cast<const uint32_t*>(pixels);
    for (size_t i = 0; i < visible_pixels.size(); ++i) visible_pixels[i] = quantise(source[i]);
    dirty = true;
    lv_display_flush_ready(display);
}
void save_frame(const std::string& path) {
    std::ofstream out(path, std::ios::binary);
    if (!out) throw std::runtime_error("Cannot create framebuffer export");
    out << "P6\n" << PW_WIDTH << ' ' << PW_HEIGHT << "\n255\n";
    for (uint32_t p : visible_pixels) {
        char rgb[3] = {static_cast<char>(p >> 16), static_cast<char>(p >> 8), static_cast<char>(p)};
        out.write(rgb, 3);
    }
    if (!out.good()) throw std::runtime_error("Framebuffer export failed");
}
void present() {
    if (!renderer || !dirty) return;
    SDL_UpdateTexture(texture, nullptr, visible_pixels.data(), PW_WIDTH * sizeof(uint32_t));
    SDL_SetRenderDrawColor(renderer, 24, 24, 24, 255);
    SDL_RenderClear(renderer);
    SDL_RenderCopy(renderer, texture, nullptr, nullptr);
    SDL_RenderPresent(renderer);
    dirty = false;
}
void command(const char* value) { std::cout << "PW:" << value << std::endl; }
void title(bool delay, uint32_t remaining = 0) {
    if (!window) return;
    std::string s = "Paperweek | Left/Right: week | T: today | R: sync | E: palette | D: delay | F: full screen | S: save";
    if (remaining) s = "Paperweek | Refresh simulation: " + std::to_string((remaining + 999) / 1000) + "s | Holding previous frame";
    else if (delay) s = "[19s refresh simulation ON] " + s;
    SDL_SetWindowTitle(window, s.c_str());
}
void ensure(bool ok, const char* message) {
    if (!ok) throw std::runtime_error(std::string(message) + ": " + SDL_GetError());
}
}

int main(int argc, char** argv) {
    umask(0077);
    std::string view_path, snapshot_path, export_path;
    float scale = 0;
    bool simulate = false;
    try {
        for (int i = 1; i < argc; ++i) {
            std::string arg = argv[i];
            auto next = [&]() -> std::string {
                if (++i >= argc) throw std::runtime_error("Missing command line value");
                return argv[i];
            };
            if (arg == "--view") view_path = next();
            else if (arg == "--snapshot") snapshot_path = next();
            else if (arg == "--export-path") export_path = next();
            else if (arg == "--scale") scale = std::stof(next());
            else if (arg == "--clean") paper = false;
            else if (arg == "--simulate-refresh") simulate = true;
            else throw std::runtime_error("Unknown command line argument");
        }
        if (view_path.empty()) throw std::runtime_error("Pass --view path/to/view.pwv");
        if (scale < 0 || scale > 2) throw std::runtime_error("Scale must be between 0 (auto) and 2");
        pw_view current = paperweek::read_view_file(view_path);
        bool headless = !snapshot_path.empty();
        if (!headless) {
            ensure(SDL_Init(SDL_INIT_VIDEO | SDL_INIT_TIMER) == 0, "SDL initialisation failed");
            SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY, "0");
            if (!scale) {
                SDL_Rect bounds{0, 0, 1280, 900};
                SDL_GetDisplayUsableBounds(0, &bounds);
                scale = std::min(0.9f * bounds.w / PW_WIDTH, 0.9f * bounds.h / PW_HEIGHT);
            }
            window = SDL_CreateWindow("Paperweek", SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
                static_cast<int>(PW_WIDTH * scale), static_cast<int>(PW_HEIGHT * scale),
                SDL_WINDOW_RESIZABLE | SDL_WINDOW_ALLOW_HIGHDPI);
            ensure(window != nullptr, "Could not create window");
            renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);
            if (!renderer) renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_SOFTWARE);
            ensure(renderer != nullptr, "Could not create renderer");
            ensure(SDL_RenderSetLogicalSize(renderer, PW_WIDTH, PW_HEIGHT) == 0, "Could not set logical size");
            texture = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_STREAMING, PW_WIDTH, PW_HEIGHT);
            ensure(texture != nullptr, "Could not create texture");
            title(simulate);
        }
        lv_init();
        lv_tick_set_cb(ticks);
        lv_display_t* display = lv_display_create(PW_WIDTH, PW_HEIGHT);
        if (!display) throw std::runtime_error("LVGL display allocation failed");
        lv_display_set_color_format(display, LV_COLOR_FORMAT_XRGB8888);
        lv_display_set_buffers(display, draw_pixels.data(), nullptr,
                              static_cast<uint32_t>(draw_pixels.size() * sizeof(uint32_t)), LV_DISPLAY_RENDER_MODE_FULL);
        lv_display_set_flush_cb(display, flush);
        pw_ui_render(&current, paper);
        lv_refr_now(display);
        if (headless) {
            save_frame(snapshot_path);
            return 0;
        }
        bool running = true, full_screen = false, pending = false;
        pw_view pending_view{};
        auto modified = std::filesystem::last_write_time(view_path);
        uint32_t last_check = 0, ready_at = 0, last_title = 0;
        present();
        while (running) {
            SDL_Event event;
            while (SDL_PollEvent(&event)) {
                if (event.type == SDL_QUIT) running = false;
                if (event.type == SDL_WINDOWEVENT) dirty = true;
                if (event.type != SDL_KEYDOWN || event.key.repeat) continue;
                switch (event.key.keysym.sym) {
                    case SDLK_ESCAPE:
                        if (full_screen) { full_screen = false; SDL_SetWindowFullscreen(window, 0); dirty = true; }
                        else running = false;
                        break;
                    case SDLK_q: running = false; break;
                    case SDLK_LEFT: command("previous"); break;
                    case SDLK_RIGHT: command("next"); break;
                    case SDLK_t: command("today"); break;
                    case SDLK_r: command("refresh"); break;
                    case SDLK_e:
                        paper = !paper; pw_ui_render(&current, paper); lv_refr_now(display); break;
                    case SDLK_d:
                        simulate = !simulate;
                        if (!simulate && pending) {
                            current = pending_view; pending = false;
                            pw_ui_render(&current, paper); lv_refr_now(display);
                        }
                        title(simulate); break;
                    case SDLK_f:
                        full_screen = !full_screen;
                        SDL_SetWindowFullscreen(window, full_screen ? SDL_WINDOW_FULLSCREEN_DESKTOP : 0);
                        dirty = true; break;
                    case SDLK_s:
                        if (!export_path.empty()) { save_frame(export_path); command("exported"); }
                        break;
                    default: break;
                }
            }
            uint32_t now = ticks();
            if (now - last_check >= 250) {
                last_check = now;
                try {
                    auto next_modified = std::filesystem::last_write_time(view_path);
                    if (next_modified != modified) {
                        modified = next_modified;
                        auto next = paperweek::read_view_file(view_path);
                        if (simulate) {
                            pending_view = next;
                            if (!pending) ready_at = now + 19000;
                            pending = true;
                        } else {
                            current = next; pw_ui_render(&current, paper); lv_refr_now(display);
                        }
                    }
                } catch (const std::exception&) {
                    // Never replace good content with an incomplete/corrupt file.
                    std::snprintf(current.status, sizeof current.status, "DISPLAY INPUT ERROR / Showing last valid frame");
                    current.stale = true; pw_ui_render(&current, paper); lv_refr_now(display);
                }
            }
            if (pending && static_cast<int32_t>(now - ready_at) >= 0) {
                current = pending_view; pending = false;
                pw_ui_render(&current, paper); lv_refr_now(display); title(simulate);
            } else if (pending && now - last_title > 250) {
                last_title = now; title(simulate, ready_at - now);
            }
            lv_timer_handler();
            present();
            SDL_Delay(12);
        }
        SDL_DestroyTexture(texture); SDL_DestroyRenderer(renderer); SDL_DestroyWindow(window); SDL_Quit();
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Paperweek preview: " << error.what() << '\n';
        if (window) SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_ERROR, "Paperweek", error.what(), window);
        SDL_Quit();
        return 1;
    }
}

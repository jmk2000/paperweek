#include "view_reader.hpp"
#include <algorithm>
#include <array>
#include <cstring>
#include <fstream>
#include <stdexcept>
#include <vector>

namespace paperweek {
namespace {
std::vector<std::string> split(const std::string& line) {
    std::vector<std::string> result;
    size_t start = 0;
    for (;;) {
        auto pos = line.find('\t', start);
        result.push_back(line.substr(start, pos == std::string::npos ? pos : pos - start));
        if (pos == std::string::npos) return result;
        start = pos + 1;
    }
}
void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}
unsigned number(const std::string& s, unsigned maximum) {
    require(!s.empty() && s.size() <= 9, "Invalid numeric field");
    unsigned n = 0;
    for (char c : s) {
        require(c >= '0' && c <= '9', "Invalid numeric field");
        n = n * 10 + static_cast<unsigned>(c - '0');
        require(n <= maximum, "Numeric field out of range");
    }
    return n;
}
pw_colour colour(const std::string& s) {
    if (s == "black") return PW_BLACK;
    if (s == "blue") return PW_BLUE;
    if (s == "red") return PW_RED;
    if (s == "green") return PW_GREEN;
    if (s == "yellow") return PW_YELLOW;
    throw std::runtime_error("Invalid calendar colour");
}
template<size_t N> void copy(char (&dest)[N], const std::string& src) {
    std::memcpy(dest, src.data(), std::min(N - 1, src.size()));
    dest[std::min(N - 1, src.size())] = '\0';
}
}
pw_view read_view(std::istream& input) {
    pw_view view{};
    std::string line;
    require(static_cast<bool>(std::getline(input, line)) && line == "PAPERWEEK1", "Unknown view format");
    std::array<bool, 7> days{};
    std::array<bool, 6> legends{};
    bool meta = false, status = false, footer = false;
    unsigned records = 0;
    while (std::getline(input, line)) {
        require(++records < 200 && line.size() <= 4096, "View exceeds protocol limits");
        for (unsigned char c : line)
            require(c == '\t' || (c >= 32 && c < 127), "View contains non-ASCII or control bytes");
        auto f = split(line);
        if (f[0] == "META") {
            require(f.size() == 8 && !meta, "Invalid metadata record"); meta = true;
            copy(view.title, f[1]); copy(view.month, f[2]); copy(view.span, f[3]);
            copy(view.week_number, f[4]); copy(view.today, f[5]); copy(view.timezone, f[6]); copy(view.mode, f[7]);
        } else if (f[0] == "LEGEND") {
            require(f.size() == 4, "Invalid legend record"); auto i = number(f[1], 5);
            require(!legends[i], "Repeated legend"); legends[i] = true;
            copy(view.calendars[i].name, f[2]); view.calendars[i].colour = colour(f[3]);
            view.calendar_count = std::max(view.calendar_count, i + 1);
        } else if (f[0] == "DAY") {
            require(f.size() == 6, "Invalid day record"); auto i = number(f[1], 6);
            require(!days[i], "Repeated day"); days[i] = true;
            copy(view.days[i].dow, f[2]); number(f[3], 31); copy(view.days[i].number, f[3]);
            view.days[i].today = number(f[4], 1) != 0; copy(view.days[i].month, f[5]);
        } else if (f[0] == "EVENT") {
            require(f.size() == 7, "Invalid event record"); auto i = number(f[1], 6);
            auto& day = view.days[i];
            require(days[i] && day.count < PW_MAX_ITEMS, "Invalid event count or ordering");
            auto& item = day.items[day.count++];
            copy(item.time, f[2]); copy(item.title, f[3]); copy(item.owner, f[4]);
            item.colour = colour(f[5]); item.all_day = number(f[6], 1) != 0;
        } else if (f[0] == "OVERFLOW") {
            require(f.size() == 3, "Invalid overflow record"); auto i = number(f[1], 6);
            view.days[i].overflow = number(f[2], 20000);
        } else if (f[0] == "FOOTER") {
            require(f.size() == 2 && !footer, "Invalid footer record"); footer = true;
            copy(view.footer, f[1]);
        } else if (f[0] == "STATUS") {
            require(f.size() == 3 && !status, "Invalid status record"); status = true;
            copy(view.status, f[1]); view.stale = number(f[2], 1) != 0;
        } else {
            throw std::runtime_error("Unrecognised view record");
        }
    }
    require(meta && footer && status, "Incomplete view");
    for (bool present : days) require(present, "Incomplete week");
    for (unsigned i = 0; i < view.calendar_count; ++i) require(legends[i], "Non-contiguous legend");
    return view;
}
pw_view read_view_file(const std::string& path) {
    std::ifstream file(path);
    require(file.good(), "Cannot read view file");
    return read_view(file);
}
}

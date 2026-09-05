#include "view_reader.hpp"
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>

namespace {
unsigned checks = 0;
void check(bool condition, const char* message) {
    ++checks;
    if (!condition) throw std::runtime_error(message);
}
std::string fixture() {
    std::string s = "PAPERWEEK1\nMETA\tOur week\tSeptember 2026\t31 Aug - 6 Sep\tWEEK 36\tSATURDAY / 5 SEP\tEurope/London\tdemo\n";
    s += "LEGEND\t0\tAlex\tblue\n";
    for (int i = 0; i < 7; ++i) {
        s += "DAY\t" + std::to_string(i) + "\tMON\t1\t0\tSEP\n";
        if (i == 0) s += "EVENT\t0\t09:00\tSchool\tAlex\tblue\t0\n";
        s += "OVERFLOW\t" + std::to_string(i) + "\t0\n";
    }
    return s + "FOOTER\tNext event\nSTATUS\tDemo\t0\n";
}
void invalid(const std::string& text) {
    bool rejected = false;
    try { std::istringstream in(text); paperweek::read_view(in); }
    catch (const std::runtime_error&) { rejected = true; }
    check(rejected, "Malformed input was accepted");
}
}
int main(int argc, char** argv) {
    try {
        if (argc == 2) {
            auto view = paperweek::read_view_file(argv[1]);
            std::cout << "Cross-language fixture accepted: " << view.title << ", " << view.month << '\n';
            return 0;
        }
        std::istringstream in(fixture());
        auto view = paperweek::read_view(in);
        check(view.calendar_count == 1, "Legend count");
        check(view.days[0].count == 1, "Event count");
        check(view.days[0].items[0].colour == PW_BLUE, "Event colour");
        check(std::string(view.title) == "Our week", "Title");
        check(!view.stale, "Stale flag");
        invalid("");
        invalid("PAPERWEEK2\n");
        invalid("PAPERWEEK1\n");
        invalid(fixture() + "DAY\t8\tMON\t1\t0\tSEP\n");
        invalid(fixture() + "DAY\t-1\tMON\t1\t0\tSEP\n");
        invalid(fixture() + "LEGEND\t6\tToo many\tblue\n");
        invalid(fixture() + "LEGEND\t1\tBad colour\tpurple\n");
        invalid(fixture() + "STATUS\tRepeated\t0\n");
        invalid(fixture() + "BAD\tUnknown\n");
        invalid(fixture() + "EVENT\t0\t10:00\tTitle\tName\tblue\t2\n");
        invalid(fixture() + "EVENT\t0\t10:00\tTitle\tName\tblue\t0\tInjected\n");
        invalid(fixture() + std::string(5000, 'A') + "\n");
        auto excessive = fixture();
        for (int i = 0; i < 6; ++i) excessive += "EVENT\t0\t12:00\tExtra\tAlex\tblue\t0\n";
        invalid(excessive);
        auto long_title = fixture();
        auto at = long_title.find("School");
        long_title.replace(at, 6, std::string(1000, 'a'));
        std::istringstream input(long_title);
        auto bounded = paperweek::read_view(input);
        check(std::string(bounded.days[0].items[0].title).size() == 191, "Bounded title copy");
        std::cout << checks << " native protocol checks passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Test failed: " << error.what() << '\n';
        return 1;
    }
}

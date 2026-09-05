#pragma once
#include "view_model.h"
#include <istream>
#include <string>
namespace paperweek {
    pw_view read_view(std::istream& input);
    pw_view read_view_file(const std::string& path);
}

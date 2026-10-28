#pragma once
#include "exclusion.hpp"
#include <string>
namespace rfr {
struct Item {
    std::string name;
    uint64_t mode;
    Input input;
    std::vector<int> truth;
};
struct Dataset {
    std::map<uint64_t, Mode> modes;
    std::vector<Item> items;
};
Dataset read_dataset(const std::string &);
Mode synthetic_mode(int, int, uint64_t = 0);
Input synthetic_input(const Mode &, double, int, int);
} // namespace rfr

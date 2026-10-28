#pragma once
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>

namespace pulse {
// Exact nonnegative value: digits * 10^exponent. Successful API results are
// canonical: no leading/trailing coefficient zeros; zero is {"0",0}.
struct DecimalOrigin {
    std::string digits = "0";
    int exponent = 0;
};
enum class OriginIssue { None, NotLiteral, Negative, BudgetExceeded, InvalidRepresentation };
struct OriginResult {
    std::optional<DecimalOrigin> value;
    OriginIssue issue = OriginIssue::None;
    explicit operator bool() const { return value.has_value(); }
};
inline constexpr size_t decimal_origin_max_digits = 4096;
inline constexpr int decimal_origin_max_exponent = 4096;
inline constexpr size_t decimal_origin_max_literal_chars = 8192;
// Intermediate integer operations have a separate explicit bound. No operation
// truncates: any final result outside the public bounds becomes unknown.
inline constexpr size_t decimal_origin_max_work_digits = 12289;
const char *origin_issue_name(OriginIssue);
OriginResult parse_decimal_origin(std::string_view literal);
OriginResult add_decimal_origins(const DecimalOrigin &, const DecimalOrigin &);
OriginResult times_decimal_origin(const DecimalOrigin &, uint64_t);
std::optional<int> compare_decimal_origins(const DecimalOrigin &, const DecimalOrigin &);
std::optional<std::string> canonical_decimal_origin(const DecimalOrigin &);
// Exact whole + tick*2^-64 + subtick*2^-128. Pass Time's three fields directly.
// A negative whole is unknown/Negative, without casting to an unsigned value.
OriginResult decimal_origin_from_binary_time(int64_t whole, uint64_t tick, uint64_t subtick);
// Provenance arithmetic only. This does not certify arbitrary fixed-expression
// evaluation, original-input conversion intervals, or continuous root times.
} // namespace pulse

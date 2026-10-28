#include "pulse/time_origin.hpp"
#include <iostream>
#include <limits>
#include <stdexcept>

namespace {
using namespace pulse;
size_t checks = 0;
void check(bool condition, const std::string &message) {
    ++checks;
    if (!condition)
        throw std::runtime_error(message);
}
DecimalOrigin known(const OriginResult &result) {
    check(bool(result.value), std::string("expected exact origin, got ") + origin_issue_name(result.issue));
    check(result.issue == OriginIssue::None, "known result has no unknown issue");
    return *result.value;
}
DecimalOrigin literal(const std::string &text) { return known(parse_decimal_origin(text)); }
void equal(const DecimalOrigin &a, const DecimalOrigin &b, const std::string &message) {
    check(compare_decimal_origins(a, b) == 0, message);
    check(canonical_decimal_origin(a) == canonical_decimal_origin(b),
          "equal exact values normalize identically");
}
void unknown(const OriginResult &result, OriginIssue issue) {
    check(!result.value && result.issue == issue, std::string("expected ") + origin_issue_name(issue));
}
} // namespace
int main() {
    try {
        using namespace pulse;
        equal(known(add_decimal_origins(literal(".1"), literal(".2"))), literal(".3"), ".1+.2=.3 exactly");
        equal(known(times_decimal_origin(literal(".01"), 100)), literal("1"), "100*.01=1 exactly");
        check(compare_decimal_origins(literal("1"), literal("1.00000000000000001")) == -1,
              "nearby decimal values remain distinct");
        check(compare_decimal_origins(literal("1.00000000000000001"), literal("1")) == 1,
              "comparison reverses sign");
        equal(literal("+000.1000"), literal("1e-1"), "positive sign/leading and trailing zeros");
        equal(literal("1."), literal("1"), "trailing decimal point");
        equal(literal(" \t+1.2500e+2\n"), literal("125"), "outer whitespace and positive exponent");
        for (const auto &text : {"0", "+0", "-0", ".0", "00.000e-100", "0T", "0f"})
            equal(literal(text), DecimalOrigin{}, "zero normalization");
        for (const auto &[with_unit, without_unit] :
             std::initializer_list<std::pair<std::string, std::string>>{{"1T", "1e12"},
                                                                        {"1G", "1e9"},
                                                                        {"1Meg", "1e6"},
                                                                        {"1MEG", "1e6"},
                                                                        {"1meg", "1e6"},
                                                                        {"1k", "1000"},
                                                                        {"1K", "1000"},
                                                                        {"1000m", "1"},
                                                                        {"1000000u", "1"},
                                                                        {"1n", "1e-9"},
                                                                        {"1p", "1e-12"},
                                                                        {"1f", "1e-15"},
                                                                        {"1.25e2k", "125000"}})
            equal(literal(with_unit), literal(without_unit), "engineering suffix exact equivalence");
        for (const auto &text : {"", ".", "+", "1M", "1s", "1MHz", "inf", "NaN", "0x1p2", "1e", "1e+", "1..0",
                                 "1 0", "+ 1", "A", "{.1+.2}", "1+2", "sin(1)"})
            unknown(parse_decimal_origin(text), OriginIssue::NotLiteral);
        unknown(parse_decimal_origin("-1"), OriginIssue::Negative);
        unknown(parse_decimal_origin("-.001u"), OriginIssue::Negative);

        const auto low_bit = known(decimal_origin_from_binary_time(0, 0, 1));
        const auto low_bit_oracle = literal("2938735877055718769921841343055614194546663891930218803771879265"
                                            "69604314863681793212890625e-128");
        equal(low_bit, low_bit_oracle, "2^-128 equals 5^128*10^-128 exactly");
        const auto one_plus_small = known(decimal_origin_from_binary_time(1, 16, 0));
        equal(one_plus_small, literal("1000000000000000000867361737988403547205962240695953369140625e-60"),
              "1+2^-60 exact origin");
        check(compare_decimal_origins(one_plus_small, literal("1")) == 1, "1+2^-60 compares above 1");
        equal(known(decimal_origin_from_binary_time(0, uint64_t(1) << 62, 0)), literal(".25"),
              "Q64 quarter second");
        equal(known(decimal_origin_from_binary_time(0, 0, 0)), literal("0"), "binary zero");
        equal(known(decimal_origin_from_binary_time(42, 0, 0)), literal("42"), "whole seconds");
        unknown(decimal_origin_from_binary_time(-1, 0, 0), OriginIssue::Negative);
        const auto max_time = known(decimal_origin_from_binary_time(std::numeric_limits<int64_t>::max(),
                                                                    std::numeric_limits<uint64_t>::max(),
                                                                    std::numeric_limits<uint64_t>::max()));
        equal(known(add_decimal_origins(max_time, low_bit)), literal("9223372036854775808"),
              "max signed whole plus all fractional bits plus 2^-128 equals 2^63");
        equal(known(add_decimal_origins(literal("1"), low_bit)),
              known(decimal_origin_from_binary_time(1, 0, 1)), "binary fraction exact add correspondence");
        const auto uintmax = std::numeric_limits<uint64_t>::max();
        equal(known(times_decimal_origin(literal("18446744073709551615"), uintmax)),
              literal("340282366920938463426481119284349108225"),
              "uint64 max product without machine overflow");
        equal(known(times_decimal_origin(literal("1e4096"), 0)), literal("0"), "zero multiplier");
        equal(known(times_decimal_origin(literal("0"), uintmax)), literal("0"), "zero operand");
        equal(known(times_decimal_origin(literal("1"), 1)), literal("1"), "identity multiplier");

        const auto max_digits = literal(std::string(decimal_origin_max_digits, '9'));
        equal(known(add_decimal_origins(max_digits, literal("1"))), literal("1e4096"),
              "long carry normalizes within exact result budget");
        unknown(times_decimal_origin(max_digits, 2), OriginIssue::BudgetExceeded);
        literal("1e4096");
        literal("1e-4096");
        unknown(parse_decimal_origin("1e4097"), OriginIssue::BudgetExceeded);
        unknown(parse_decimal_origin("1e-4097"), OriginIssue::BudgetExceeded);
        unknown(parse_decimal_origin("1e9999999999999999999999999999"), OriginIssue::BudgetExceeded);
        unknown(parse_decimal_origin(std::string(decimal_origin_max_digits + 1, '1')),
                OriginIssue::BudgetExceeded);
        unknown(parse_decimal_origin(std::string(decimal_origin_max_literal_chars + 1, '0')),
                OriginIssue::BudgetExceeded);
        equal(literal(std::string(decimal_origin_max_literal_chars - 1, '0') + "1"), literal("1"),
              "largest literal input with normalized short coefficient");
        unknown(add_decimal_origins(literal("1e4096"), literal("1e-4096")), OriginIssue::BudgetExceeded);
        unknown(add_decimal_origins(literal("5e4096"), literal("5e4096")), OriginIssue::BudgetExceeded);
        for (const DecimalOrigin &bad :
             {DecimalOrigin{"", 0}, DecimalOrigin{"01", 0}, DecimalOrigin{"10", 0}, DecimalOrigin{"1x", 0},
              DecimalOrigin{"0", 1}, DecimalOrigin{"1", 4097}}) {
            unknown(add_decimal_origins(bad, literal("1")), OriginIssue::InvalidRepresentation);
            unknown(times_decimal_origin(bad, 1), OriginIssue::InvalidRepresentation);
            check(!compare_decimal_origins(bad, literal("1")), "invalid exact object cannot be compared");
            check(!canonical_decimal_origin(bad),
                  "invalid exact object cannot be normalized by pretending valid");
        }
        // Small exact integer grid is an independent built-in integer oracle.
        for (uint64_t a = 0; a <= 20; ++a)
            for (uint64_t b = 0; b <= 20; ++b) {
                equal(known(add_decimal_origins(literal(std::to_string(a)), literal(std::to_string(b)))),
                      literal(std::to_string(a + b)), "integer add grid");
                equal(known(times_decimal_origin(literal(std::to_string(a)), b)),
                      literal(std::to_string(a * b)), "integer multiply grid");
                check(compare_decimal_origins(literal(std::to_string(a)), literal(std::to_string(b))) ==
                          (a < b   ? -1
                           : a > b ? 1
                                   : 0),
                      "integer comparison grid");
            }
        std::cout << "PASS time origin " << checks << " checks\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "FAIL time origin " << error.what() << '\n';
        return 1;
    }
}

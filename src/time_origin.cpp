#include "pulse/time_origin.hpp"
#include <algorithm>
#include <array>
#include <cstdint>
#include <cctype>
#include <limits>
#include <vector>

namespace pulse {
namespace {
OriginResult unknown(OriginIssue issue) { return {std::nullopt, issue}; }
bool valid(const DecimalOrigin &value) {
    if (value.digits.empty() || value.digits.size() > decimal_origin_max_digits ||
        value.exponent < -decimal_origin_max_exponent || value.exponent > decimal_origin_max_exponent)
        return false;
    if (!std::all_of(value.digits.begin(), value.digits.end(), [](char c) { return c >= '0' && c <= '9'; }))
        return false;
    if (value.digits == "0")
        return value.exponent == 0;
    return value.digits.front() != '0' && value.digits.back() != '0';
}
OriginResult normalize(std::string digits, int exponent) {
    const auto first = digits.find_first_not_of('0');
    if (first == std::string::npos)
        return {DecimalOrigin{}, OriginIssue::None};
    digits.erase(0, first);
    const auto last = digits.find_last_not_of('0');
    exponent += int(digits.size() - last - 1);
    digits.erase(last + 1);
    if (digits.size() > decimal_origin_max_digits || exponent < -decimal_origin_max_exponent ||
        exponent > decimal_origin_max_exponent)
        return unknown(OriginIssue::BudgetExceeded);
    return {DecimalOrigin{std::move(digits), exponent}, OriginIssue::None};
}
// Decimal integer arithmetic; each intermediate is bounded by max_work_digits.
std::optional<std::string> add_digits(const std::string &a, const std::string &b) {
    const auto size = std::max(a.size(), b.size());
    if (size + 1 > decimal_origin_max_work_digits)
        return std::nullopt;
    std::string result(size, '0');
    int carry = 0;
    for (size_t offset = 0; offset < size; ++offset) {
        int sum = carry;
        if (offset < a.size())
            sum += a[a.size() - offset - 1] - '0';
        if (offset < b.size())
            sum += b[b.size() - offset - 1] - '0';
        result[size - offset - 1] = char('0' + sum % 10);
        carry = sum / 10;
    }
    if (carry)
        result.insert(result.begin(), char('0' + carry));
    return result;
}
std::optional<std::string> multiply_digits(const std::string &a, const std::string &b) {
    if (a.size() + b.size() > decimal_origin_max_work_digits)
        return std::nullopt;
    // In this module b is at most 20 digits (a uint64_t). Individual cells
    // accumulate at most 20*81, so there is no machine-width product overflow.
    std::vector<unsigned> work(a.size() + b.size(), 0);
    for (size_t i = 0; i < a.size(); ++i)
        for (size_t j = 0; j < b.size(); ++j)
            work[i + j + 1] += unsigned(a[i] - '0') * unsigned(b[j] - '0');
    for (size_t i = work.size() - 1; i > 0; --i) {
        work[i - 1] += work[i] / 10;
        work[i] %= 10;
    }
    std::string result;
    result.reserve(work.size());
    for (unsigned digit : work)
        result += char('0' + digit);
    const auto first = result.find_first_not_of('0');
    return first == std::string::npos ? std::string("0") : result.substr(first);
}
} // namespace

const char *origin_issue_name(OriginIssue issue) {
    switch (issue) {
    case OriginIssue::None:
        return "KNOWN";
    case OriginIssue::NotLiteral:
        return "UNKNOWN_NOT_LITERAL";
    case OriginIssue::Negative:
        return "UNKNOWN_NEGATIVE";
    case OriginIssue::BudgetExceeded:
        return "UNKNOWN_BUDGET_EXCEEDED";
    case OriginIssue::InvalidRepresentation:
        return "UNKNOWN_INVALID_REPRESENTATION";
    }
    return "UNKNOWN_INVALID_ISSUE";
}
OriginResult parse_decimal_origin(std::string_view input) {
    if (input.size() > decimal_origin_max_literal_chars)
        return unknown(OriginIssue::BudgetExceeded);
    while (!input.empty() && std::isspace(static_cast<unsigned char>(input.front())))
        input.remove_prefix(1);
    while (!input.empty() && std::isspace(static_cast<unsigned char>(input.back())))
        input.remove_suffix(1);
    if (input.empty())
        return unknown(OriginIssue::NotLiteral);
    size_t index = 0;
    bool negative = false;
    if (input[index] == '+' || input[index] == '-')
        negative = input[index++] == '-';
    std::string digits;
    bool dot = false;
    int fractional_digits = 0;
    while (index < input.size()) {
        const char c = input[index];
        if (c >= '0' && c <= '9') {
            digits += c;
            if (dot)
                ++fractional_digits;
            ++index;
        } else if (c == '.' && !dot) {
            dot = true;
            ++index;
        } else
            break;
    }
    if (digits.empty())
        return unknown(OriginIssue::NotLiteral);
    int exponent = 0;
    if (index < input.size() && (input[index] == 'e' || input[index] == 'E')) {
        ++index;
        bool minus = false;
        if (index < input.size() && (input[index] == '+' || input[index] == '-'))
            minus = input[index++] == '-';
        const auto start = index;
        while (index < input.size() && input[index] >= '0' && input[index] <= '9') {
            const int digit = input[index++] - '0';
            if (exponent > (int(decimal_origin_max_literal_chars) - digit) / 10)
                return unknown(OriginIssue::BudgetExceeded);
            exponent = exponent * 10 + digit;
        }
        if (index == start)
            return unknown(OriginIssue::NotLiteral);
        if (minus)
            exponent = -exponent;
    }
    const auto suffix = input.substr(index);
    int unit = 0;
    if (suffix.empty()) {
    } else if (suffix == "T")
        unit = 12;
    else if (suffix == "G")
        unit = 9;
    else if (suffix == "Meg" || suffix == "meg" || suffix == "MEG")
        unit = 6;
    else if (suffix == "k" || suffix == "K")
        unit = 3;
    else if (suffix == "m")
        unit = -3;
    else if (suffix == "u")
        unit = -6;
    else if (suffix == "n")
        unit = -9;
    else if (suffix == "p")
        unit = -12;
    else if (suffix == "f")
        unit = -15;
    else
        return unknown(OriginIssue::NotLiteral);
    auto result = normalize(std::move(digits), exponent - fractional_digits + unit);
    if (negative && result.value && result.value->digits != "0")
        return unknown(OriginIssue::Negative);
    return result;
}
OriginResult add_decimal_origins(const DecimalOrigin &a, const DecimalOrigin &b) {
    if (!valid(a) || !valid(b))
        return unknown(OriginIssue::InvalidRepresentation);
    if (a.digits == "0")
        return {b, OriginIssue::None};
    if (b.digits == "0")
        return {a, OriginIssue::None};
    const int exponent = std::min(a.exponent, b.exponent);
    std::string left = a.digits, right = b.digits;
    const auto left_zeros = size_t(a.exponent - exponent), right_zeros = size_t(b.exponent - exponent);
    if (left.size() + left_zeros >= decimal_origin_max_work_digits ||
        right.size() + right_zeros >= decimal_origin_max_work_digits)
        return unknown(OriginIssue::BudgetExceeded);
    left.append(left_zeros, '0');
    right.append(right_zeros, '0');
    auto digits = add_digits(left, right);
    return digits ? normalize(std::move(*digits), exponent) : unknown(OriginIssue::BudgetExceeded);
}
OriginResult times_decimal_origin(const DecimalOrigin &a, uint64_t multiplier) {
    if (!valid(a))
        return unknown(OriginIssue::InvalidRepresentation);
    if (!multiplier || a.digits == "0")
        return {DecimalOrigin{}, OriginIssue::None};
    auto digits = multiply_digits(a.digits, std::to_string(multiplier));
    return digits ? normalize(std::move(*digits), a.exponent) : unknown(OriginIssue::BudgetExceeded);
}
std::optional<int> compare_decimal_origins(const DecimalOrigin &a, const DecimalOrigin &b) {
    if (!valid(a) || !valid(b))
        return std::nullopt;
    if (a.digits == "0" || b.digits == "0")
        return a.digits == b.digits ? 0 : a.digits == "0" ? -1 : 1;
    const int order_a = int(a.digits.size()) + a.exponent;
    const int order_b = int(b.digits.size()) + b.exponent;
    if (order_a != order_b)
        return order_a < order_b ? -1 : 1;
    for (size_t i = 0; i < std::max(a.digits.size(), b.digits.size()); ++i) {
        const char left = i < a.digits.size() ? a.digits[i] : '0';
        const char right = i < b.digits.size() ? b.digits[i] : '0';
        if (left != right)
            return left < right ? -1 : 1;
    }
    return 0;
}
std::optional<std::string> canonical_decimal_origin(const DecimalOrigin &a) {
    if (!valid(a))
        return std::nullopt;
    return a.digits == "0" ? "0" : a.digits + "e" + std::to_string(a.exponent);
}
OriginResult decimal_origin_from_binary_time(int64_t whole, uint64_t tick, uint64_t subtick) {
    if (whole < 0)
        return unknown(OriginIssue::Negative);
    // Exact identity: (whole*2^128 + tick*2^64 + subtick)/2^128
    // = (whole*2^128 + tick*2^64 + subtick)*5^128 * 10^-128.
    // 192 bits + ceil(log2(5^128)) = at most 490 bits. Sixteen 32-bit
    // limbs therefore hold every supported nonnegative T128 input exactly.
    using Limbs = std::array<std::uint32_t, 16>;
    static const Limbs five_to_128 = [] {
        Limbs factor{};
        factor[0] = 1;
        for (int step = 0; step < 128; ++step) {
            std::uint64_t carry = 0;
            for (auto &limb : factor) {
                const std::uint64_t product = std::uint64_t(limb) * 5 + carry;
                limb = std::uint32_t(product);
                carry = product >> 32;
            }
        }
        return factor;
    }();
    const std::uint64_t w = std::uint64_t(whole);
    const Limbs input = {
        std::uint32_t(subtick), std::uint32_t(subtick >> 32),
        std::uint32_t(tick), std::uint32_t(tick >> 32),
        std::uint32_t(w), std::uint32_t(w >> 32)
    };
    Limbs integer{};
    for (size_t i = 0; i < 6; ++i) {
        std::uint64_t carry = 0;
        for (size_t j = 0; j < integer.size() - i; ++j) {
            const std::uint64_t product = std::uint64_t(input[i]) * five_to_128[j]
                + integer[i + j] + carry;
            integer[i + j] = std::uint32_t(product);
            carry = product >> 32;
        }
        // The 490-bit bound proves that no nonzero carry can exit 512 bits.
    }
    // Convert the exact 512-bit integer to decimal in base-10^9 chunks.
    std::vector<std::uint32_t> chunks;
    chunks.reserve(18);
    for (;;) {
        bool nonzero = false;
        for (const auto limb : integer) nonzero |= limb != 0;
        if (!nonzero) break;
        std::uint64_t remainder = 0;
        for (size_t i = integer.size(); i-- > 0;) {
            const std::uint64_t dividend = (remainder << 32) | integer[i];
            integer[i] = std::uint32_t(dividend / 1000000000ULL);
            remainder = dividend % 1000000000ULL;
        }
        chunks.push_back(std::uint32_t(remainder));
    }
    if (chunks.empty()) return {DecimalOrigin{}, OriginIssue::None};
    std::string digits = std::to_string(chunks.back());
    for (size_t i = chunks.size() - 1; i-- > 0;) {
        auto part = std::to_string(chunks[i]);
        digits.append(9 - part.size(), '0');
        digits += part;
    }
    return normalize(std::move(digits), -128);
}
} // namespace pulse

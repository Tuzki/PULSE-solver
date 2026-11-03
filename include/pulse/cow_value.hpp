#pragma once
#include <memory>
#include <utility>

namespace pulse {
// A transaction-local, copy-on-write owner. Copying a CowValue is O(1).
// All readers receive const references; mutable access explicitly detaches.
// No shared mutable state may cross a transaction or retry boundary.
template<class T>
class CowValue {
 public:
  CowValue() : value_(std::make_shared<T>()) {}
  CowValue(const T& value) : value_(std::make_shared<T>(value)) {}
  CowValue(T&& value) : value_(std::make_shared<T>(std::move(value))) {}
  CowValue(const CowValue&) noexcept = default;
  CowValue(CowValue&&) noexcept = default;
  CowValue& operator=(const CowValue&) noexcept = default;
  CowValue& operator=(CowValue&&) noexcept = default;
  CowValue& operator=(const T& value) {
    value_ = std::make_shared<T>(value);
    return *this;
  }
  CowValue& operator=(T&& value) {
    value_ = std::make_shared<T>(std::move(value));
    return *this;
  }
  const T& read() const noexcept { return *value_; }
  T& edit() {
    if (!value_.unique()) value_ = std::make_shared<T>(*value_);
    return *value_;
  }
  bool shares_storage_with(const CowValue& other) const noexcept {
    return value_ == other.value_;
  }
  long storage_references() const noexcept { return value_.use_count(); }
 private:
  std::shared_ptr<T> value_;
};
} // namespace pulse

#ifndef _SAFARI_COMMON_H_
#define _SAFARI_COMMON_H_

#include <unistd.h>
#include <cstdio>
#include <cstdlib>
#include <string>

#define CHECK(condition) check_impl(condition, #condition, __FILE__, __LINE__)

#ifdef DEBUG
#define dprintf(...) printf(__VA_ARGS__)
#else
#define dprintf(...)
#endif

namespace safari {
namespace {
using std::string;

void check_impl(bool condition, const char* condition_str, const char* file,
                int line) {
  if (!!!condition) {
    fprintf(stderr, "[CHECK:%s:%d]: %s\n", file, line, condition_str);
    exit(1);
  }
}

int string_to_int(const char* str) {
  char* end;
  auto result = std::strtol(str, &end, 10);
  CHECK(*end == '\0');
  return result;
}

}  // namespace
}  // namespace safari
#endif  // _SAFARI_COMMON_H_

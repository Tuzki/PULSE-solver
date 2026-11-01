#include "pulse/software.hpp"
#include <bit>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
int main(int argc, char **argv) {
  std::cout << "{\"pointer_bits\":" << sizeof(void*)*8
            << ",\"double_digits\":" << std::numeric_limits<double>::digits
            << ",\"long_double_bytes\":" << sizeof(long double)
            << ",\"long_double_digits\":" << std::numeric_limits<long double>::digits
            << ",\"long_double_max_exponent\":" << std::numeric_limits<long double>::max_exponent
            << ",\"long_double_epsilon\":" << std::numeric_limits<long double>::epsilon()
            << ",\"little_endian\":" << (std::endian::native==std::endian::little?"true":"false")
            << "}\n";
  if(sizeof(void*)!=8 || std::numeric_limits<double>::digits!=53)
    throw std::runtime_error("x86-64 binary64 platform required");
#if defined(__linux__) && defined(__x86_64__)
  if(std::numeric_limits<long double>::digits!=64 ||
     std::numeric_limits<long double>::max_exponent!=16384 ||
     1.0L+std::ldexp(1.0L,-63)==1.0L)
    throw std::runtime_error("expected x86-64 extended long double unavailable");
#endif
  if(argc==2) {
    auto path=std::filesystem::path(argv[1]);
    {std::ofstream f(path,std::ios::binary);f<<"abc";}
    if(pulse::software::file_sha256(path.string())!=
       "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
      throw std::runtime_error("SHA256 known vector failed");
    {std::ofstream f(path,std::ios::binary);}
    if(pulse::software::file_sha256(path.string())!=
       "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
      throw std::runtime_error("SHA256 empty vector failed");
    constexpr size_t large=65*1024*1024;
    {std::ofstream f(path,std::ios::binary);f.seekp(large-1);f.put('\0');}
    bool rejected=false;try{pulse::software::file_sha256(path.string());}
    catch(const std::exception&e){if(pulse::diagnostic(e).at("subcode")!="SOFTWARE_FILE_SIZE")throw;rejected=true;}
    if(!rejected)throw std::runtime_error("oversized module accepted");
    if(pulse::software::file_sha256(path.string(),large)!=
       "25631f11bd18756ec0029380ec886af0c8824dc6b2706bbdb1d9451c7cf45f42")throw std::runtime_error("streamed SHA256 vector failed");
    rejected=false;try{pulse::software::file_sha256(path.string(),large-1);}
    catch(const std::exception&e){if(pulse::diagnostic(e).at("subcode")!="SOFTWARE_FILE_SIZE")throw;rejected=true;}
    if(!rejected)throw std::runtime_error("archive size bound bypassed");
    std::filesystem::remove(path);
  }
}

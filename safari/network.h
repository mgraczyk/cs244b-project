#ifndef _SAFARI_NETWORK_H_
#define _SAFARI_NETWORK_H_

#include "common.h"

#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
#include <string>
#include <cstring>

namespace safari {
namespace {
using std::string;

string sockaddr_to_string(const sockaddr_in& addr) {
  char buf[INET_ADDRSTRLEN];
  CHECK(inet_ntop(AF_INET, &addr, &buf[0], sizeof(buf)));
  return string{buf, std::strlen(buf)} + ":" + std::to_string(addr.sin_port);
}
}  // namespace

class UDPMessage final {
 public:
  UDPMessage() = default;
  UDPMessage(UDPMessage&&) = default;

  int recv(int socket) {
    socklen_t addrlen = sizeof(addr_);
    const auto recvlen =
        recvfrom(socket, buf_, kBufferSize, 0,
                 reinterpret_cast<sockaddr*>(&addr_), &addrlen);
    CHECK(addrlen == sizeof(addr_));
    CHECK(recvlen > 0);
    CHECK(recvlen < static_cast<ssize_t>(kBufferSize));

    size_ = recvlen;
    return size_;
  }

  int send(int socket) const {
    dprintf("sending %zu bytes to %s\n", size_, addr_str().c_str());
    CHECK(size_ > 0);
    const auto bytes_sent =
        sendto(socket, buf_, size_, 0, (sockaddr*)&addr_, sizeof(addr_));
    CHECK(bytes_sent == static_cast<ssize_t>(size_));
    return 1;
  }

  void set_reply_string(const std::string& s) {
    CHECK(s.size() < kBufferSize);
    std::copy(s.begin(), s.end(), buf_);
    size_ = s.size();
  }
  void set_size(size_t size) {
    CHECK(size <= kBufferSize);
    size_ = size;
  };

  void copy_addr_from(const UDPMessage& other) { addr_ = other.addr(); };

  size_t max_size() const { return kBufferSize; };
  size_t size() const { return size_; };
  const uint8_t* data() const { return buf_; };
  uint8_t* data() { return buf_; };
  sockaddr_in addr() const { return addr_; };

  string addr_str() const { return sockaddr_to_string(addr_); };
  string data_str() const { return string{(char*)&buf_[0], size_}; }

 private:
  constexpr static size_t kBufferSize = 8192;

  // Disallow copy.
  UDPMessage(UDPMessage&) = delete;

  uint8_t buf_[kBufferSize] = {};
  size_t size_ = 0;
  sockaddr_in addr_ = {};
};

class UDPSocket final {
 public:
  UDPSocket(int port) : port_{port}, fd_(socket(AF_INET, SOCK_DGRAM, 0)) {
    CHECK(fd_ > 0);

    my_addr_.sin_family = AF_INET;
    my_addr_.sin_addr.s_addr = htonl(INADDR_ANY);
    my_addr_.sin_port = htons(port_);

    CHECK(bind(fd_, (sockaddr*)&my_addr_, sizeof(my_addr_)) >= 0);
  }

  ~UDPSocket() { close(fd_); }

  int receive_one(UDPMessage* message) {
    CHECK(message);
    CHECK(message->recv(fd_));

    return 1;
  }

  int send_one(const UDPMessage& message) {
    CHECK(message.send(fd_));
    return 1;
  }

 private:
  const int port_;
  const int fd_;
  sockaddr_in my_addr_;
};

}  // namespace safari

#endif  // _SAFARI_NETWORK_H_

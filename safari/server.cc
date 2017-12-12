#include "common.h"
#include "network.h"
#include "zk_types.h"

#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <set>
#include <string>
#include <unordered_set>
#include <vector>
#include <utility>
#include <memory>


#define offsetof(type, member) ((size_t)((&(((type*)(nullptr))->member))))


namespace safari {
namespace {
using std::map;

std::pair<string, string> split_path(const string& path) {
  auto pos = path.rfind("/", 0);
  string parent;
  string node_name;
  if (pos != string::npos && pos > 0) {
    return {path.substr(0, pos), path.substr(pos)};
  } else {
    return {"/", path};
  }
}
}  // namespace

class ZRequest {
 public:
  ZRequest(std::unique_ptr<UDPMessage> message)
      : udp_message_{std::move(message)} {}

  const ZRequestMessage& req() const {
    return *reinterpret_cast<const ZRequestMessage*>(udp_message_->data());
  }

  string path() const {
    ssize_t last_non_del = req().path_sz - 1;
    for (; last_non_del > 0 && req().path[last_non_del] == '/'; --last_non_del)
      ;

    return string{&req().path[0], static_cast<size_t>(last_non_del + 1)};
  };

  std::unique_ptr<UDPMessage> release_udp_message() {
    return std::move(udp_message_);
  }

  const UDPMessage& udp_message() const { return *udp_message_; }

 private:
  std::unique_ptr<UDPMessage> udp_message_{};
};

class ZResponse {
 public:
  ZResponse(std::unique_ptr<UDPMessage> message)
      : udp_message_{std::move(message)} {}

  ZResponseMessage* message() {
    return reinterpret_cast<ZResponseMessage*>(udp_message_->data());
  }

  const ZResponseMessage& message() const {
    return *reinterpret_cast<const ZResponseMessage*>(udp_message_->data());
  }

  void reply_to(const ZRequest& request) {
    message()->request_id = request.req().id;
    udp_message_->copy_addr_from(request.udp_message());
  }

  void reply_with(const ZRequest& request, ZMessageType message_type,
                  size_t size) {
    reply_to(request);
    message()->message_type = message_type;
    message()->error_type = ZMessageErrorType::NoError;
    CHECK(size >= offsetof(ZResponseMessage, header_end));
    udp_message_->set_size(size);
  }

  void reply_with(const ZRequest& request, ZMessageErrorType error_type) {
    reply_to(request);
    message()->message_type = ZMessageType::Error;
    message()->error_type = error_type;
    udp_message_->set_size(offsetof(ZResponseMessage, header_end));
  }

  std::unique_ptr<UDPMessage> release_udp_message() {
    return std::move(udp_message_);
  }

  const UDPMessage& udp_message() { return *udp_message_; }

 private:
  std::unique_ptr<UDPMessage> udp_message_{};
};

class ZNode final {
 public:
  ZNode(string path, string data)
      : path_{path}, data_{data}, stat_{}, child_node_names_() {}

  ZNodeStat stat() const { return stat_; }
  const string& data_str() const { return data_; }

  void add_child(string path) { child_node_names_.emplace(std::move(path)); }
  void set_data(const char* buf, size_t sz) {
    data_ = string{buf, sz};
    ++stat_.version;
  }

 private:
  const string path_;
  string data_;
  ZNodeStat stat_;

  std::set<string> child_node_names_;
};

class ZTree final {
 public:
  ZTree() : nodes_by_path_{} {
    // Insert the root.
    nodes_by_path_.try_emplace("/", "/", "");
  }

  bool path_exists(const string& path) const {
    return nodes_by_path_.count(path);
  }

  ZMessageErrorType get_data_into(const string& path, char* buf, size_t buf_sz,
                                  uint64_t* out_sz, ZNodeStat* stat_out) const {
    CHECK(out_sz);
    CHECK(stat_out);
    auto search = nodes_by_path_.find(path);
    if (search == nodes_by_path_.end()) {
      dprintf("Can't get_data: %s node is missing\n", path.c_str());
      return ZMessageErrorType::NoNode;
    }

    const auto& node = search->second;
    const size_t bytes_to_write = node.data_str().size();
    *stat_out = node.stat();
    *out_sz = bytes_to_write;
    CHECK(bytes_to_write <= buf_sz);
    std::copy(node.data_str().begin(), node.data_str().begin() + bytes_to_write,
              buf);
    dprintf("get_data_into wrote %zu bytes\n", bytes_to_write);

    return ZMessageErrorType::NoError;
  }

  ZMessageErrorType set_data(const string& path, const char* buf, size_t buf_sz,
                             ZNodeStat* stat_out) {
    CHECK(stat_out);
    auto search = nodes_by_path_.find(path);
    if (search == nodes_by_path_.end()) {
      dprintf("Can't set_data: %s node is missing\n", path.c_str());
      return ZMessageErrorType::NoNode;
    }

    auto& node = search->second;
    node.set_data(buf, buf_sz);
    *stat_out = node.stat();

    return ZMessageErrorType::NoError;
  }

  ZMessageErrorType create_node(const string& path, string data) {
    string parent_path;
    string node_name;
    std::tie(parent_path, node_name) = split_path(path);

    // Make sure the parent exists.
    auto parent_search = nodes_by_path_.find(parent_path);
    if (parent_search == nodes_by_path_.end()) {
      dprintf("Can't create %s because parent %s is missing\n", path.c_str(),
              parent_path.c_str());
      return ZMessageErrorType::NoNode;
    }

    // Create the new node.
    auto insertion_result =
        nodes_by_path_.try_emplace(path, path, std::move(data));
    if (!insertion_result.second) {
      return ZMessageErrorType::NodeExists;
    }

    // Insert as parent's child.
    parent_search->second.add_child(std::move(node_name));
    return ZMessageErrorType::NoError;
  }

 private:
  ZTree(ZTree&) = delete;

  std::map<string, ZNode> nodes_by_path_;
};

class Server final {
 public:
  struct Args {
    static Args FromCommandLine(int argc, const char** argv) {
      CHECK(argc == 2);
      auto result = Args{};
      result.port = string_to_int(argv[1]);
      return result;
    }

    int port;
  };

  Server(Args args) : args_{args} {}

  void run_forever();

 private:
  Server(Server&) = delete;

  void ping(const ZRequest& request, ZResponse* response) {
    const auto reply_data = "pingback: " + request.udp_message().data_str();
    std::copy(reply_data.begin(), reply_data.end(),
              response->message()->ping.data);
    response->reply_with(
        request, ZMessageType::PingResponse,
        offsetof(ZResponseMessage, ping.data) + reply_data.size());
  }

  void create(const ZRequest& request, ZResponse* response) {
    auto path = request.path();
    if (tree_.path_exists(path)) {
      dprintf("Can't create %s because it exists\n", path.c_str());
      response->reply_with(request, ZMessageErrorType::NodeExists);
    }

    const auto err = tree_.create_node(std::move(path), request.path().c_str());
    if (err != ZMessageErrorType::NoError) {
      response->reply_with(request, err);
      return;
    }
    dprintf("Create %s ok\n", request.path().c_str());
    response->reply_with(request, ZMessageType::CreateResponse,
                         offsetof(ZResponseMessage, create));
  }

  void get_data(const ZRequest& request, ZResponse* response) {
    auto path = request.path();
    auto* message = response->message();

    const auto header_size = offsetof(ZResponseMessage, get_data.data);
    const auto max_sz = response->udp_message().max_size() - header_size;
    const auto err = tree_.get_data_into(path, message->get_data.data, max_sz,
                                         &message->get_data.data_sz,
                                         &message->get_data.stat);
    if (err != ZMessageErrorType::NoError) {
      response->reply_with(request, err);
      return;
    }
    response->reply_with(request, ZMessageType::GetDataResponse,
                         header_size + message->get_data.data_sz);
  }

  void set_data(const ZRequest& request, ZResponse* response) {
    auto path = request.path();
    auto* message = response->message();

    const auto err =
        tree_.set_data(path, &request.req().set_data.data[0],
                       request.req().set_data.data_sz, &message->set_data.stat);
    if (err != ZMessageErrorType::NoError) {
      response->reply_with(request, err);
      return;
    }

    const auto message_size = offsetof(ZResponseMessage, set_data.stat) +
                              sizeof(ZResponseMessage::set_data.stat);
    response->reply_with(request, ZMessageType::SetDataResponse, message_size);
  }

  const Args args_;
  ZTree tree_;
};

void Server::run_forever() {
  UDPSocket udp_socket{args_.port};
  auto udp_message = std::make_unique<UDPMessage>();
  auto response_message = std::make_unique<UDPMessage>();

  for (;;) {
    dprintf("Receiving on port %d\n", args_.port);
    CHECK(udp_socket.receive_one(udp_message.get()));
    dprintf("Received %zu byte message from %s: \"%s\"\n", udp_message->size(),
            udp_message->addr_str().c_str(), udp_message->data_str().c_str());

    ZRequest request{std::move(udp_message)};
    ZResponse response{std::move(response_message)};

    switch (request.req().message_type) {
      case ZMessageType::Ping: {
        dprintf("Got ping request\n");
        ping(request, &response);
        break;
      }
      case ZMessageType::Create: {
        dprintf("Got create request\n");
        create(request, &response);
        break;
      }
      case ZMessageType::Exists: {
        dprintf("Got exists request\n");
        CHECK(0);
        break;
      }
      case ZMessageType::GetData: {
        dprintf("Got getData request\n");
        get_data(request, &response);
        break;
      }
      case ZMessageType::SetData: {
        dprintf("Got setData request\n");
        set_data(request, &response);
        break;
      }
      default: {
        printf("Got unknown message type: %llu\n", (long long unsigned int)request.req().message_type);
        response.reply_with(request, ZMessageErrorType::BadRequest);
        break;
      }
    }
    CHECK(udp_socket.send_one(response.udp_message()));

    udp_message = request.release_udp_message();
    response_message = response.release_udp_message();
  }
}

}  // namespace safari

using namespace safari;

int main(int argc, const char** argv) {
  const auto args = Server::Args::FromCommandLine(argc, argv);
  Server(args).run_forever();

  return 0;
}

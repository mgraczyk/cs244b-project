#include "common.h"
#include "network.h"
#include "types.capnp.h"

#include <arpa/inet.h>
#include <capnp/message.h>
#include <capnp/serialize-packed.h>
#include <kj/string.h>
#include <netinet/in.h>
#include <poll.h>
#include <unistd.h>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <memory>
#include <set>
#include <sstream>
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>

namespace safari {

struct ZNodeStat final {
  uint64_t czxid;
  uint64_t mzxid;
  uint64_t ctime;
  uint64_t mtime;
  uint64_t version;
  uint64_t cversion;
  uint64_t aversion;
  uint64_t ephemeralOwner;
  uint64_t dataLength;
  uint64_t numChildren;
  uint64_t pzxid;
} __attribute__((__aligned__(sizeof(capnp::word))));
static_assert(sizeof(ZNodeStat) == 88);

using DataPtr = kj::ArrayPtr<uint8_t>;
using ConstDataPtr = kj::ArrayPtr<const uint8_t>;

namespace {
using std::map;
using std::tuple;
using std::vector;

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

vector<string> parse_comma_separated(const std::string& str) {
  std::stringstream ss(str);
  vector<string> result{};

  string item;
  while (ss.good()) {
    getline(ss, item, ',');
    if (!item.empty()) {
      result.emplace_back(std::move(item));
    }
  }
  return result;
}

template <typename T>
ZNodeStat* get_stat_ptr(T& t) {
  uint8_t* stat_buffer = t.initStat(sizeof(ZNodeStat)).begin();
  return reinterpret_cast<ZNodeStat*>(stat_buffer);
}

}  // namespace

class ZRequest final {
 public:
  ZRequest(std::unique_ptr<UDPMessage> message)
      : udp_message_(std::move(message)),
        message_reader_(kj::ArrayPtr<capnp::word>(
            reinterpret_cast<capnp::word*>(udp_message_->data()),
            udp_message_->size())) {}

  uint64_t id() { return reader().getId(); }
  ZRequestMessage::Reader body() { return reader(); }

  string path() {
    const char* path_cstr = reader().getPath().cStr();
    ssize_t last_non_del = reader().getPath().size() - 1;
    for (; last_non_del > 0 && path_cstr[last_non_del] == '/'; --last_non_del)
      ;

    return string{path_cstr, static_cast<size_t>(last_non_del + 1)};
  };

  const UDPMessage& udp_message() const { return *udp_message_; }

  std::unique_ptr<UDPMessage> release_udp_message() {
    return std::move(udp_message_);
  }

 private:
  ZRequestMessage::Reader reader() {
    return message_reader_.getRoot<ZRequestMessage>();
  }

  std::unique_ptr<UDPMessage> udp_message_{};
  capnp::FlatArrayMessageReader message_reader_;
};

class ZResponse final {
 public:
  class Finished {
   private:
    friend class ZResponse;
    Finished() = default;
  };

  ZResponse(std::unique_ptr<UDPMessage> message)
      : udp_message_{std::move(message)},
        message_builder_{},
        builder_{message_builder_.getRoot<ZResponseMessage>()} {}

  ZResponseMessage::Reader reader() const { return builder_.asReader(); }
  ZResponseMessage::Builder builder() { return builder_; }
  ZResponseMessage::Builder body() { return builder_; }

  Finished reply_with_error(ZRequest& request, ZErrorType error_type) {
    body().setError(error_type);
    return finish(request);
  }

  Finished done(ZRequest& request) {
    CHECK(body().which() != ZResponseMessage::Which::UNKNOWN);
    return finish(request);
  }

  std::unique_ptr<UDPMessage> release_udp_message() {
    return std::move(udp_message_);
  }

  const UDPMessage& udp_message() { return *udp_message_; }

 private:
  size_t size() {
    return capnp::computeSerializedSizeInWords(message_builder_) *
           sizeof(capnp::word);
  }

  Finished finish(ZRequest& request) {
    builder_.setRequestId(request.id());
    udp_message_->copy_addr_from(request.udp_message());

    auto output_stream =
        kj::ArrayOutputStream({udp_message_->data(), udp_message_->max_size()});
    capnp::writeMessage(output_stream, message_builder_);
    dprintf("Size is %zu\n", size());
    udp_message_->set_size(output_stream.getArray().size());
    return {};
  }

  std::unique_ptr<UDPMessage> udp_message_{};
  capnp::MallocMessageBuilder message_builder_;
  ZResponseMessage::Builder builder_;
};

class ZNode final {
 public:
  ZNode(string path, string data)
      : path_{path}, data_{data}, stat_{}, child_node_names_() {}

  ZNodeStat stat() const { return stat_; }
  const string& data_str() const { return data_; }

  void add_child(string path) { child_node_names_.emplace(std::move(path)); }
  void set_data(ConstDataPtr data) {
    data_ = string{reinterpret_cast<const char*>(data.begin()), data.size()};
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

  ZErrorType get_data(const string& path, string* data_out,
                      ZNodeStat* stat_out) const {
    CHECK(data_out);
    CHECK(stat_out);
    auto search = nodes_by_path_.find(path);
    if (search == nodes_by_path_.end()) {
      dprintf("Can't get_data: %s node is missing\n", path.c_str());
      return ZErrorType::NO_NODE;
    }

    const auto& node = search->second;
    *stat_out = node.stat();
    *data_out = node.data_str();
    dprintf("get_data wrote %zu bytes\n", node.data_str().size());

    return ZErrorType::NO_ERROR;
  }

  ZErrorType set_data(const string& path, ConstDataPtr data,
                      ZNodeStat* stat_out) {
    CHECK(stat_out);
    auto search = nodes_by_path_.find(path);
    if (search == nodes_by_path_.end()) {
      dprintf("Can't set_data: %s node is missing\n", path.c_str());
      return ZErrorType::NO_NODE;
    }

    auto& node = search->second;
    node.set_data(data);
    *stat_out = node.stat();

    return ZErrorType::NO_ERROR;
  }

  ZErrorType create_node(const string& path, string data) {
    string parent_path;
    string node_name;
    std::tie(parent_path, node_name) = split_path(path);

    // Make sure the parent exists.
    auto parent_search = nodes_by_path_.find(parent_path);
    if (parent_search == nodes_by_path_.end()) {
      dprintf("Can't create %s because parent %s is missing\n", path.c_str(),
              parent_path.c_str());
      return ZErrorType::NO_NODE;
    }

    // Create the new node.
    auto insertion_result =
        nodes_by_path_.try_emplace(path, path, std::move(data));
    if (!insertion_result.second) {
      return ZErrorType ::NODE_EXISTS;
    }

    // Insert as parent's child.
    parent_search->second.add_child(std::move(node_name));
    return ZErrorType ::NO_ERROR;
  }

 private:
  ZTree(ZTree&) = delete;

  map<string, ZNode> nodes_by_path_;
};

class Server final {
 public:
  struct Args {
    static Args FromCommandLine(int argc, const char** argv) {
      CHECK(argc == 3);
      auto result = Args{};
      result.port = string_to_int(argv[1]);
      result.peer_addresses = parse_comma_separated(argv[2]);
      return result;
    }

    int port;
    vector<string> peer_addresses;
  };

  Server(Args args)
      : args_{args},
        num_nodes_{static_cast<int>(args.peer_addresses.size() + 1)},
        quorum_size_{num_nodes_ / 2 + 1},
        txid_{0} {
    (void)txid_;
  }

  void run_forever();

 private:
  Server(Server&) = delete;

  ZResponse::Finished ping(ZRequest& request, ZResponse* response) {
    const auto data = request.body().getPing().getData();
    const auto reply_data =
        string("pingback: ") +
        string(reinterpret_cast<const char*>(data.begin()), data.size());

    dprintf("Created reply_data '%s'\n", reply_data.c_str());
    response->body().initPing().setData(
        {reinterpret_cast<const uint8_t*>(reply_data.data()),
         reply_data.size()});
    return response->done(request);
  }

  ZResponse::Finished create(ZRequest& request, ZResponse* response) {
    auto path = request.path();
    if (tree_.path_exists(path)) {
      dprintf("Can't create %s because it exists\n", path.c_str());
      return response->reply_with_error(request, ZErrorType::NODE_EXISTS);
    }

    const auto err = tree_.create_node(std::move(path), request.path().c_str());
    if (err != ZErrorType::NO_ERROR) {
      return response->reply_with_error(request, err);
    }

    dprintf("Create %s ok\n", request.path().c_str());
    response->body().setCreate();
    return response->done(request);
  }

  ZResponse::Finished exists(ZRequest& request, ZResponse* response) {
    auto path = request.path();
    const auto exists = tree_.path_exists(path);

    response->body().getExists().setExists(exists);
    return response->done(request);
  }

  ZResponse::Finished get_data(ZRequest& request, ZResponse* response) {
    auto path = request.path();
    auto message = response->body().initGetData();
    auto* stat_ptr = get_stat_ptr(message);

    string result_data;
    const auto err = tree_.get_data(path, &result_data, stat_ptr);
    if (err != ZErrorType::NO_ERROR) {
      return response->reply_with_error(request, err);
    }

    message.setData({(const uint8_t*)result_data.data(), result_data.size()});
    return response->done(request);
  }

  ZResponse::Finished set_data(ZRequest& request, ZResponse* response) {
    auto path = request.path();
    auto data = request.body().getSetData().getData();
    auto message = response->body().initSetData();
    auto* stat_ptr = get_stat_ptr(message);

    const auto err = tree_.set_data(path, data, stat_ptr);
    if (err != ZErrorType::NO_ERROR) {
      return response->reply_with_error(request, err);
    }

    return response->done(request);
  }

  const Args args_;
  const int num_nodes_;
  const int quorum_size_;
  uint64_t txid_;
  ZTree tree_;
};

void Server::run_forever() {
  UDPSocket send_sock{};
  UDPSocket recv_sock{args_.port};
  auto request_message = std::make_unique<UDPMessage>();
  auto response_message = std::make_unique<UDPMessage>();

  printf("Receiving on port %d with %zu peers ", args_.port,
         args_.peer_addresses.size());
  for (const auto& peer_address : args_.peer_addresses) {
    printf("%s,", peer_address.c_str());
  }
  puts("");
  printf("Quorum size is %d\n", quorum_size_);

  //XXX POLL
  for (;;) {
    CHECK(recv_sock.receive_one(request_message.get()));
    dprintf("Received %zu byte message from %s: \"%s\"\n",
            request_message->size(), request_message->addr_str().c_str(),
            request_message->data_str().c_str());

    ZRequest request{std::move(request_message)};
    ZResponse response{std::move(response_message)};

    switch (request.body().which()) {
      case ZRequestMessage::PING: {
        dprintf("Got ping request\n");
        ping(request, &response);
        break;
      }
      case ZRequestMessage::CREATE: {
        dprintf("Got create request\n");
        create(request, &response);
        break;
      }
      case ZRequestMessage::EXISTS: {
        dprintf("Got exists request\n");
        exists(request, &response);
        break;
      }
      case ZRequestMessage::GET_DATA: {
        dprintf("Got getData request with id %llu\n", request.id());
        get_data(request, &response);
        break;
      }
      case ZRequestMessage::SET_DATA: {
        dprintf("Got setData request with id %llu\n", request.id());
        set_data(request, &response);
        break;
      }
      case ZRequestMessage::DELETE_CMD: {
        dprintf("Got delete request with id %llu\n", request.id());
        response.reply_with_error(request, ZErrorType::NOT_IMPLEMENTED);
        break;
      }
      case ZRequestMessage::GET_CHILDREN: {
        dprintf("Got getChildren request with id %llu\n", request.id());
        response.reply_with_error(request, ZErrorType::NOT_IMPLEMENTED);
        break;
      }
      case ZRequestMessage::SYNC: {
        dprintf("Got sync request with id %llu\n", request.id());
        response.reply_with_error(request, ZErrorType::NOT_IMPLEMENTED);
        break;
      }
      default: {
        printf("Got unknown message type: %llu\n",
               (long long unsigned int)request.body().which());
        response.reply_with_error(request, ZErrorType::BAD_REQUEST);
        break;
      }
    }
    CHECK(recv_sock.send_one(response.udp_message()));

    dprintf("Responding to request id %llu with %d, response id %llu\n",
            request.id(), response.body().which(),
            response.reader().getRequestId());

    request_message = request.release_udp_message();
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

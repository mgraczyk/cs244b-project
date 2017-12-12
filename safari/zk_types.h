#ifndef _SAFARI_ZK_TYPES_H_
#define _SAFARI_ZK_TYPES_H_

#define PATH_LEN 256

namespace safari {

enum class ZMessageType : uint64_t {
  Unknown,
  Error = 1,

  Ping = 100,
  Create = 101,
  Delete = 102,
  Exists = 103,
  GetData = 104,
  SetData = 105,
  GetChildren = 106,
  Sync = 107,

  PingResponse = 200,
  CreateResponse = 201,
  DeleteResponse = 202,
  ExistsResponse = 203,
  GetDataResponse = 204,
  SetDataResponse = 205,
  GetChildrenResponse = 206,
  SyncResponse = 207,
};

enum class ZMessageErrorType : uint64_t {
  Unknown,
  NoError = 1,
  BadRequest = 2,
  NodeExists = 3,
  NoNode = 4,
};

struct ZNodeStat {
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
};
static_assert(sizeof(ZNodeStat) == 88);

struct ZRequestMessage {
  uint64_t id;
  ZMessageType message_type;
  uint64_t path_sz;
  char path[PATH_LEN];

  union {
    struct {
      char data[];
    } ping;
    struct {
      uint64_t data_sz;
      char data[];
    } create;
    struct {
      int64_t version;
    } delete_cmd;
    struct {
    } exists;
    struct {
    } get_data;
    struct {
      int64_t version;
      uint64_t data_sz;
      char data[];
    } set_data;
    struct {
    } get_children;
    struct {
    } sync;
  };
};

struct ZResponseMessage {
  uint64_t request_id;
  ZMessageErrorType error_type;
  ZMessageType message_type;

  union {
    struct {
    } header_end;
    struct {
      char data[];
    } ping;
    struct {
    } create;
    struct {
    } delete_cmd;
    struct {
    } exists;
    struct {
      ZNodeStat stat;
      uint64_t data_sz;
      char data[];
    } get_data;
    struct {
      ZNodeStat stat;
    } set_data;
  };
};

}  // namespace safari
#endif  // _SAFARI_ZK_TYPES_H_

@0xf584e2b6254da5df;

using Cxx = import "c++.capnp";
$Cxx.namespace("safari");

enum ZErrorType {
  unknown @0;
  noError @1;
  badRequest @2;
  notImplemented @3;
  nodeExists @4;
  noNode @5;
}

#struct ZNodeStat {
#  czxid @0 :UInt64;
#  mzxid @1 :UInt64;
#  ctime @2 :UInt64;
#  mtime @3 :UInt64;
#  version @4 :UInt64;
#  cversion @5 :UInt64;
#  aversion @6 :UInt64;
#  ephemeralOwner @7 :UInt64;
#  dataLength @8 :UInt64;
#  numChildren @9 :UInt64;
#  pzxid @10 :UInt64;
#}

struct JustData {
  data @0 :Data;
}

struct ZRequestMessage {
  id @0 :UInt64;
  path @1 :Text;

  union {
    unknown @2 :Void;
    ping @3 :Text;
    create @4 :JustData;
    deleteCmd @5 :Delete;
    exists @6 :Void;
    getData @7 :Void;
    setData @8 :SetData;
    getChildren @9 :Void;
    sync @10 :Void;
  }

  struct Delete {
    version @0 :Int64;
  }

  struct SetData {
    version @0 :Int64;
    data @1 :Data;
  }
}

struct ZResponseMessage {
  requestId @0 :UInt64;

  union {
    unknown @1 :Void;
  	error @2 :ZErrorType;
    ping @3 :Text;
    create @4 :Void;
    deleteCmd @5 :Void;
    exists @6 :Exists;
    getData @7 :GetData;
    setData @8 :SetData;
    getChildren @9 :Void;
    sync @10 :Void;
  }

  struct Exists {
    exists @0 :Bool;
  }

  struct GetData {
    stat @0 :Data;
    data @1 :Data;
  }

  struct SetData {
    stat @0 :Data;
  }
}

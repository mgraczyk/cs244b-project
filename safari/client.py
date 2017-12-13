import sys
import itertools
import struct
import time
from socket import socket, AF_INET, SOCK_DGRAM
from collections import defaultdict
from kazoo.protocol.states import ZnodeStat

if sys.platform == 'darwin':
  from select import (poll as epoll, POLLIN as EPOLLIN, POLLOUT as EPOLLOUT,
                      POLLERR as EPOLLERR, POLLHUP as EPOLLHUP)
else:
  from select import epoll, EPOLLIN, EPOLLOUT, EPOLLERR, EPOLLHUP

_PATH_LEN = 256

_MESSAGE_TYPE_ERROR = struct.pack('<Q', 1)
_MESSAGE_TYPE_PING = struct.pack('<Q', 100)
_MESSAGE_TYPE_CREATE = struct.pack('<Q', 101)
_MESSAGE_TYPE_DELETE = struct.pack('<Q', 102)
_MESSAGE_TYPE_EXISTS = struct.pack('<Q', 103)
_MESSAGE_TYPE_GET_DATA = struct.pack('<Q', 104)
_MESSAGE_TYPE_SET_DATA = struct.pack('<Q', 105)
_MESSAGE_TYPE_GET_CHILDREN = struct.pack('<Q', 106)
_MESSAGE_TYPE_SYNC = struct.pack('<Q', 106)

_MESSAGE_TYPE_PING_RESPONSE = struct.pack('<Q', 200)
_MESSAGE_TYPE_CREATE_RESPONSE = struct.pack('<Q', 201)
_MESSAGE_TYPE_DELETE_RESPONSE = struct.pack('<Q', 202)
_MESSAGE_TYPE_EXISTS_RESPONSE = struct.pack('<Q', 203)
_MESSAGE_TYPE_GET_DATA_RESPONSE = struct.pack('<Q', 204)
_MESSAGE_TYPE_SET_DATA_RESPONSE = struct.pack('<Q', 205)
_MESSAGE_TYPE_ET_CHILDREN_RESPONSE = struct.pack('<Q', 206)
_MESSAGE_TYPE_SYNC_RESPONSE = struct.pack('<Q', 207)

_ERROR_TYPE_UNKNOWN = struct.pack('<Q', 1)
_ERROR_TYPE_NO_ERROR = struct.pack('<Q', 1)
_ERROR_TYPE_BAD_REQUEST = struct.pack('<Q', 2)
_ERROR_TYPE_NOT_IMPLEMENTED = struct.pack('<Q', 3)
_ERROR_TYPE_NODE_EXISTS = struct.pack('<Q', 4)
_ERROR_TYPE_NO_NODE = struct.pack('<Q', 5)


class SafariException(Exception): pass
class UnknownError(SafariException): pass
class BadRequestError(SafariException): pass
class NodeExistsError(SafariException): pass
class NoNodeError(SafariException): pass

_ERROR_TYPES_TO_EXCEPTION = {
    _ERROR_TYPE_UNKNOWN: UnknownError,
    _ERROR_TYPE_NO_ERROR: None,
    _ERROR_TYPE_BAD_REQUEST: BadRequestError,
    _ERROR_TYPE_NOT_IMPLEMENTED: NotImplementedError,
    _ERROR_TYPE_NODE_EXISTS: NodeExistsError,
    _ERROR_TYPE_NO_NODE: NoNodeError
}

def _err_to_exception(err):
  exception = _ERROR_TYPES_TO_EXCEPTION[err]
  if exception:
    raise exception


def _parse_znode_stat(data):
  stat = ZnodeStat(*map(b_to_uint, (data[8*i:8*(i + 1)] for i in range(11))))
  return data[88:], stat



def create_socket(addr):
  sock = socket(AF_INET, SOCK_DGRAM)
  sock.settimeout(10.)
  sock.connect(addr)
  return sock

def b_to_int(b):
  return struct.unpack('<q', b)[0]

def b_to_uint(b):
  return struct.unpack('<Q', b)[0]

def int_to_b(i):
  return struct.pack('<q', i)

def uint_to_b(i):
  return struct.pack('<Q', i)

def assert_type(message_type, expected_type):
  if message_type != expected_type:
    raise Exception(b_to_uint(message_type))



class SafariClient(object):

  def __init__(self, hosts):
    if isinstance(hosts, str):
      hosts = [hosts]

    addr_pairs = [h.split(':') for h in hosts]

    self._hosts = [(p[0], int(p[1])) for p in addr_pairs]
    self._socks = list(map(create_socket, self._hosts))
    self._fds_to_hosts = {
        s.fileno(): self._hosts[i]
        for i, s in enumerate(self._socks)
    }
    self._fds_to_sock = {s.fileno(): s for i, s in enumerate(self._socks)}
    self._id = itertools.count()
    self._poll = epoll()
    for fd in self._fds_to_sock:
      self._poll.register(fd, EPOLLIN | EPOLLERR | EPOLLHUP)
    self._N = len(self._socks)
    self._quorum = self._N // 2 + 1

  def start(self):
    pass

  def ping(self, message):
    message_type, data = self._do_send(_MESSAGE_TYPE_PING, b'', message)
    assert_type(message_type, _MESSAGE_TYPE_PING_RESPONSE)
    return data

  def create(self, path, data=b''):
    message_type, data = self._do_send(_MESSAGE_TYPE_CREATE, path,
                                       uint_to_b(len(data)), data)
    assert_type(message_type, _MESSAGE_TYPE_CREATE_RESPONSE)
    return path

  def ensure_path(self, path):
    parts = path.split('/')
    base = ''
    for p in parts:
      if not p:
        continue
      base = '/' + p

      try:
        self.create(path)
      except NodeExistsError:
        pass

    return True

  def exists(self, path):
    message_type, data = self._do_send(_MESSAGE_TYPE_EXISTS, path)
    assert_type(message_type, _MESSAGE_TYPE_EXISTS_RESPONSE)
    exists = any(data[:8])
    return exists

  def get(self, path):
    message_type, data = self._do_send(_MESSAGE_TYPE_GET_DATA, path)
    assert_type(message_type, _MESSAGE_TYPE_GET_DATA_RESPONSE)
    rest, stat = _parse_znode_stat(data)
    result_data = rest[8:]
    assert b_to_uint(rest[:8]) == len(result_data)
    return result_data, stat

  def set(self, path, data, version=-1):
    message_type, data = self._do_send(_MESSAGE_TYPE_SET_DATA, path,
                                       int_to_b(version),
                                       uint_to_b(len(data)), data)
    assert_type(message_type, _MESSAGE_TYPE_SET_DATA_RESPONSE)
    rest, stat = _parse_znode_stat(data)
    assert len(rest) == 0
    return stat

  def _do_send(self, message_type_bytes, path, *args):
    if isinstance(path, str):
      path = bytes(path, 'utf-8')

    id_bytes = struct.pack('<Q', next(self._id))
    to_send = b''.join((id_bytes, message_type_bytes, uint_to_b(len(path)),
                        path, bytes(_PATH_LEN - len(path))) + args)

    for s in self._socks:
      try:
        s.send(to_send)
      except ConnectionRefusedError:
        print('Got ConnectionRefusedError on send')
        pass

    results = defaultdict(list)
    received_from = set()

    poller = self._poll
    f = self._quorum
    end = time.time() + 10.
    while sum(len(v) for v in results.values()) < f:
      evts = poller.poll(10.)
      if not evts:
        if time.time() > end:
          raise TimeoutError()
        else:
          continue

      for fd, evt in evts:
        if evt == EPOLLIN:
          try:
            data, server = self._fds_to_sock[fd].recvfrom(2048)
          except ConnectionRefusedError:
            print('Got ConnectionRefusedError on recv')
            continue
          request_id, error_type, message_type = (data[:8], data[8:16],
                                                  data[16:24])
          if request_id != id_bytes:
            continue

          # Check whether we've received from this host in case of duplicate messages.
          host = self._fds_to_hosts[fd]
          if host not in received_from:
            received_from.add(host)
            results[error_type, message_type].append(data[24:])
        else:
          raise Exception('Got unexpected event {} on {}'.format(evt, fd))

    for k, v in results.items():
      if len(v) >= f:
        _err_to_exception(k[0])
        assert all(vv == v[0]
                   for vv in v[1:]), {(b_to_uint(k[0]), b_to_uint(k[1])): v
                                      for k, v in results.items()}
        return k[1], v[0]
    assert False, {(b_to_uint(k[0]), b_to_uint(k[1])): v
                   for k, v in results.items()}

    return data

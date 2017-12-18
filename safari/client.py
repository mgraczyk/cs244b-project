import os
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

import capnp
capnp.remove_import_hook()
types = capnp.load(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "types.capnp"))


class SafariException(Exception): pass
class UnknownError(SafariException): pass
class BadRequestError(SafariException): pass
class NodeExistsError(SafariException): pass
class NoNodeError(SafariException): pass


_ERROR_TYPES_TO_EXCEPTION = {
    0: UnknownError,
    1: None,
    2: BadRequestError,
    3: NotImplementedError,
    4: NodeExistsError,
    5: NoNodeError
}


def _err_to_exception(err):
  exception = _ERROR_TYPES_TO_EXCEPTION[err.raw]
  if exception:
    raise exception


def _b_to_uint(b):
  return struct.unpack('<Q', b)[0]


def _parse_znode_stat(data):
  return ZnodeStat(*map(_b_to_uint, (data[8 * i:8 * (i + 1)]
                                     for i in range(11))))


def create_socket(addr):
  sock = socket(AF_INET, SOCK_DGRAM)
  sock.settimeout(10.)
  sock.connect(addr)
  return sock


def check_error(response):
  if response.which() == 'error':
    _err_to_exception(response.error)


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

  def ping(self, message):
    request = types.ZRequestMessage.new_message()
    request.init('ping').data = message
    response = self._do_send(request, '', True)

    return response.ping.data

  def create(self, path, data=b''):
    request = types.ZRequestMessage.new_message()
    request.init('create').data = data
    response = self._do_send(request, path, False)
    return path

  def exists(self, path):
    request = types.ZRequestMessage.new_message()
    request.exists = None
    response = self._do_send(request, path, True)
    return response.exists.exists

  def get(self, path):
    request = types.ZRequestMessage.new_message()
    request.getData = None
    response = self._do_send(request, path, True)
    stat = _parse_znode_stat(response.getData.stat)
    return response.getData.data, stat

  def set(self, path, data, version=-1):
    request = types.ZRequestMessage.new_message()
    set_data = request.init('setData')
    set_data.version = version
    set_data.data = data
    response = self._do_send(request, path, False)
    return _parse_znode_stat(response.setData.stat)

  def _do_send(self, request, path, is_read):
    request_id = next(self._id)

    request.id = request_id
    request.path = path
    to_send = request.to_bytes()

    for s in self._socks:
      try:
        s.send(to_send)
      except ConnectionRefusedError:
        print('Got ConnectionRefusedError on send')
        pass

    results = defaultdict(list)
    received_from = set()

    poller = self._poll
    f = 1 if is_read else self._quorum
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
          response = types.ZResponseMessage.from_bytes(data)
          if response.requestId != request_id:
            continue

          # Check whether we've received from this host in case of duplicate messages.
          host = self._fds_to_hosts[fd]
          if host not in received_from:
            received_from.add(host)
            results[response.which()].append(response)
        else:
          raise Exception('Got unexpected event {} on {}'.format(evt, fd))

    for k, v in results.items():
      if len(v) >= f:
        assert all(vv == v[0] for vv in v[1:]), v
        check_error(v[0])
        return v[0]

    check_error(response)
    return response

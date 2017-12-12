import time
from safari.client import SafariClient
from kazoo.client import KazooClient

from benchmark import print_latencies

def _pp(v, n):
  print('{}: {} {}'.format(n, v[0], v[1].version))


def test_inconsistent(client_type, hosts):
  client_a = client_type([hosts[0], hosts[1]])
  client_a.start()

  client_a.ensure_path('/test')
  client_a.set('/test', b'data a')
  client_a.set('/test', b'data a')
  a1 = client_a.get('/test')
  _pp(a1, 'a1')

  client_b = client_type([hosts[0], hosts[2]])
  client_b.start()
  b1 = client_b.get('/test')
  _pp(b1, 'b1')

  client_b.set('/test', b'data b')
  a2 = client_a.get('/test')
  b2 = client_b.get('/test')
  _pp(a2, 'a2')
  _pp(b2, 'b2')

  client_c = client_type([hosts[1], hosts[2]])
  client_c.start()
  client_c.set('/test', b'data c')

  c1 = client_c.get('/test')
  _pp(c1, 'c1')

  a3 = client_a.get('/test')
  b3 = client_b.get('/test')
  c2 = client_c.get('/test')
  _pp(a3, 'a3')
  _pp(b3, 'b3')
  _pp(c2, 'c2')

zk_hosts=['127.0.0.1:2181', '127.0.0.1:2182', '127.0.0.1:2183']
test_inconsistent(KazooClient, zk_hosts)

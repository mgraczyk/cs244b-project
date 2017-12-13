import os
import sys
import numpy as np
import subprocess
import kazoo
from kazoo.client import KazooClient

from safari.client import SafariClient


def _run_background_client(client_type, hosts, num_nodes):
  client = client_type(hosts=hosts)
  client.start()

  print('Running out of process client')
  get_func = client.get
  set_func = client.set
  np_random_randint = np.random.randint
  while True:
    r, w = np_random_randint(num_nodes, size=(2,))
    result = get_func('/latency_test/node_{}'.format(r))
    if w % 2 == 0:
      data = result[0][:-1] or b'x'
    else:
      data = result[0] + b'x'
    set_func('/latency_test/node_{}'.format(w), data)


if __name__ == '__main__':
  assert len(sys.argv) == 4
  client_type_name = sys.argv[1]
  hosts = sys.argv[2].split(',')
  num_nodes = int(sys.argv[3])

  if client_type_name == 'KazooClient':
    client_type = KazooClient
  elif client_type_name == 'SafariClient':
    client_type = SafariClient
  else:
    raise ValueError(client_type_name)

  _run_background_client(client_type, hosts, num_nodes)

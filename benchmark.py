import os
import kazoo
import numpy as np
import time
import logging
from tqdm import tqdm
from kazoo.client import KazooClient

from safari.client import SafariClient

logger = logging.getLogger(__name__)
now = time.time

def print_latencies(latencies_seconds):
  latencies_ms = 1000 * np.array(latencies_seconds)
  print('Average Latency = {} ms'.format(np.mean(latencies_ms)))
  print('Median Latency =  {} ms'.format(np.median(latencies_ms)))
  print('99% Latency =     {} ms'.format(np.percentile(latencies_ms, 99.)))
  print('99.9% Latency =  {} ms'.format(np.percentile(latencies_ms, 99.9)))


def test_latency(client):
  np.random.seed(1337)
  num_nodes = 5
  node_size = 100
  num_read_samples = 1000
  num_write_samples = 50

  client.ensure_path('/latency_test/')

  node_data = [np.random.bytes(node_size) for _ in range(num_nodes)]
  for i in range(num_nodes):
    path = '/latency_test/node_{}'.format(i)
    client.ensure_path(path)
    client.set(path, node_data[i])

  print('Testing Read Latency')
  samples = np.random.randint(num_nodes, size=(num_read_samples,)).tolist()
  latencies = []
  get_func = client.get
  for s in tqdm(samples):
    before = now()
    result = get_func('/latency_test/node_{}'.format(s))
    after = now()
    assert result[0] == node_data[s], (s, result[0], node_data[s])
    latencies.append(after - before)

  print_latencies(latencies)
  print('')


  print('Testing Write Latency')
  samples = np.random.randint(num_nodes, size=(num_write_samples,)).tolist()
  latencies = []
  set_func = client.set
  for s in tqdm(samples):
    data = np.random.bytes(node_size)
    before = now()
    result = set_func('/latency_test/node_{}'.format(s), data)
    after = now()
    latencies.append(after - before)

  print_latencies(latencies)
  print('')

def main():
  print('Testing Zookeeper latency')
  zk = KazooClient(hosts=['127.0.0.1:2181', '127.0.0.1:2182', '127.0.0.1:2183'])
  zk.start()
  test_latency(zk)
  print('')

  print('Testing Safari latency')
  # sf = SafariClient(hosts='127.0.0.1:12000')
  sf = SafariClient(
      hosts=['127.0.0.1:12000', '127.0.0.1:12001', '127.0.0.1:12002'])
  sf.start()
  test_latency(sf)
  print('')


if __name__ == '__main__':
  main()

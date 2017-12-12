import os
import sys
import kazoo
import numpy as np
import time
import logging
from tqdm import tqdm
from kazoo.client import KazooClient
from matplotlib import pyplot as plt
import seaborn as sns

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

  f, (ax1, ax2, ax3) = plt.subplots(3, sharex=True, sharey=False)
  for ax in (ax1, ax2, ax3):
    ax.set_xscale('log')

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
  sns.distplot(latencies, ax=ax1)
  ax1.set_ylabel('Read')
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
  sns.distplot(latencies, ax=ax2)
  ax2.set_ylabel('Write')
  print('')


  print('Testing Read Modify Write Latency')
  samples = np.random.randint(num_nodes, size=(num_read_samples, 2))
  latencies = []
  for i in tqdm(range(samples.shape[0])):
    r, w = samples[i]
    before = now()
    result = get_func('/latency_test/node_{}'.format(r))
    if w % 2 == 0:
      data = result[0][:-1] or b'x'
    else:
      data = result[0] + b'x'
    set_func('/latency_test/node_{}'.format(w), data)
    after = now()
    latencies.append(after - before)

  print_latencies(latencies)
  sns.distplot(latencies, ax=ax3)
  ax3.set_ylabel('Mixed')
  print('')

  f.subplots_adjust(hspace=0)
  plt.setp([a.get_xticklabels() for a in f.axes[:-1]], visible=False)
  ax3.set_xlabel('time (ms)')
  return ax1

def main():
  if len(sys.argv) < 2:
    test = 'local'
  else:
    test = sys.argv[1]

  if sys.platform == 'darwin':
    zoo1 = 'ec2-54-183-150-149.us-west-1.compute.amazonaws.com'
    zoo2 = 'ec2-54-67-113-246.us-west-1.compute.amazonaws.com'
    zoo3 = 'ec2-54-82-116-157.us-west-1.compute.amazonaws.com'
  else:
    zoo1 = '172.31.7.146'
    zoo2 = '172.31.13.236'
    zoo3 = '54.82.116.157'

  if test == 'local':
    zk_hosts = ['127.0.0.1:2181', '127.0.0.1:2182', '127.0.0.1:2183']
    safari_hosts = ['127.0.0.1:12000', '127.0.0.1:12001', '127.0.0.1:12002']
  elif test == 'local_one':
    zk_hosts = ['127.0.0.1:2181']
    safari_hosts = ['127.0.0.1:12000']
  elif test == 'exp1':
    zk_hosts = [
        '{}:2181'.format(zoo1), '{}:2181'.format(zoo2), '{}:2181'.format(zoo3)
    ]
    zk_hosts = [
        '{}:12000'.format(zoo1), '{}:12000'.format(zoo2),
        '{}:12000'.format(zoo3)
    ]
  else:
    raise NotImplementedError(test)

  print('Testing Zookeeper latency')
  zk = KazooClient(hosts=zk_hosts)
  zk.start()
  f = test_latency(zk)
  f.set_title('Zookeeper Latency')
  print('')

  print('Testing Safari latency')
  sf = SafariClient(hosts=safari_hosts)
  sf.start()
  f = test_latency(sf)
  f.set_title('Safari Latency')
  print('')

  plt.show()


if __name__ == '__main__':
  main()

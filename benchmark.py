import os
import sys
import kazoo
import numpy as np
import time
import logging
import subprocess
from tqdm import tqdm
from kazoo.client import KazooClient

try:
  from matplotlib import pyplot as plt
  import seaborn as sns
  _DO_PLOTS = True
except ImportError:
  _DO_PLOTS = False
  pass

from safari.client import SafariClient

logger = logging.getLogger(__name__)
now = time.time

def print_latencies(latencies_seconds):
  latencies_ms = 1000 * np.array(latencies_seconds)
  print('Average Latency = {} ms'.format(np.mean(latencies_ms)))
  print('Median Latency =  {} ms'.format(np.median(latencies_ms)))
  print('99% Latency =     {} ms'.format(np.percentile(latencies_ms, 99.)))
  print('99.9% Latency =  {} ms'.format(np.percentile(latencies_ms, 99.9)))


def test_latency(client_type, hosts):
  client = client_type(hosts=hosts)
  client.start()

  np.random.seed(1337)
  num_nodes = 5
  node_size = 100
  num_read_samples = 1000
  num_write_samples = 50
  num_other_procs = 5

  client.ensure_path('/latency_test/')

  node_data = [np.random.bytes(node_size) for _ in range(num_nodes)]
  for i in range(num_nodes):
    path = '/latency_test/node_{}'.format(i)
    client.ensure_path(path)
    client.set(path, node_data[i])

  print('Testing Read Latency')
  samples = np.random.randint(num_nodes, size=(num_read_samples,)).tolist()
  read_latencies = []
  get_func = client.get
  for s in tqdm(samples):
    before = now()
    result = get_func('/latency_test/node_{}'.format(s))
    after = now()
    assert result[0] == node_data[s], (s, result[0], node_data[s])
    read_latencies.append(after - before)

  print_latencies(read_latencies)
  print('')


  print('Testing Write Latency')
  samples = np.random.randint(num_nodes, size=(num_write_samples,)).tolist()
  write_latencies = []
  set_func = client.set
  for s in tqdm(samples):
    data = np.random.bytes(node_size)
    before = now()
    result = set_func('/latency_test/node_{}'.format(s), data)
    after = now()
    write_latencies.append(after - before)
  print_latencies(write_latencies)
  print('')


  print('Testing Read Modify Write Latency')
  procs = [
      subprocess.Popen(
          [
              sys.executable,
              os.path.join(
                  os.path.dirname(__file__), 'run_conflicting_client.py'),
              client_type.__name__, ','.join(hosts),
              str(num_nodes)
          ],
          close_fds=True) for _ in range(num_other_procs)
  ]
  time.sleep(2.)

  samples = np.random.randint(num_nodes, size=(num_read_samples, 2))
  mixed_latencies = []
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
    mixed_latencies.append(after - before)
  print_latencies(mixed_latencies)
  print('')

  for proc in procs:
    proc.terminate()
  for proc in procs:
    proc.wait()

  if _DO_PLOTS:
    f, (ax1, ax2, ax3) = plt.subplots(3, sharex=True, sharey=False)
    for ax in (ax1, ax2, ax3):
      ax.set_xscale('log')
      ax.set_xlim([5e-5, 5e-2])

    sns.distplot(read_latencies, ax=ax1)
    sns.distplot(write_latencies, ax=ax2)
    sns.distplot(mixed_latencies, ax=ax3)

    ax1.set_ylabel('Read')
    ax2.set_ylabel('Write')
    ax3.set_ylabel('Mixed')

    f.subplots_adjust(hspace=0)
    plt.setp([a.get_xticklabels() for a in f.axes[:-1]], visible=False)
    ax3.set_xlabel('time (ms)')
    return ax1
  else:
    return (read_latencies, write_latencies, mixed_latencies)

def main():
  if len(sys.argv) < 2:
    test = 'local'
  else:
    test = sys.argv[1]

  if sys.platform == 'darwin':
    # zoo1 = 'ec2-54-183-150-149.us-west-1.compute.amazonaws.com'
    # zoo2 = 'ec2-54-67-113-246.us-west-1.compute.amazonaws.com'
    # zoo3 = 'ec2-54-82-116-157.us-west-1.compute.amazonaws.com'
    zoo1 = '54.183.150.149'
    zoo2 = '54.67.113.246'
    zoo3 = '54.82.116.157'
    zoo4 = '52.34.167.196'
  else:
    zoo1 = '172.31.7.146'
    zoo2 = '172.31.13.236'
    zoo3 = '54.82.116.157'
    zoo4 = '52.34.167.196'

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
    safari_hosts = [
        '{}:12000'.format(zoo1), '{}:12000'.format(zoo2),
        '{}:12000'.format(zoo3)
    ]
  elif test == 'exp2':
    zk_hosts = [
        '{}:2181'.format(zoo4), '{}:2181'.format(zoo2), '{}:2181'.format(zoo3)
    ]
    safari_hosts = [
        '{}:12000'.format(zoo4), '{}:12000'.format(zoo2),
        '{}:12000'.format(zoo3)
    ]
  else:
    raise NotImplementedError(test)

  print('Testing Zookeeper latency')
  zk_fig = test_latency(KazooClient, zk_hosts)
  print('')

  print('Testing Safari latency')
  sf_fig = test_latency(SafariClient, safari_hosts)
  print('')

  if _DO_PLOTS:
    zk_fig.set_title('Zookeeper Latency')
    sf_fig.set_title('Safari Latency')
    plt.show()
  else:
    for name, results in (('zookeeper', zk_fig), ('safari', sf_fig)):
      for kind, result in zip(('read', 'write', 'mixed'), results):
        np.savetxt('{}.{}.csv'.format(name, kind), result, delimiter=',')

if __name__ == '__main__':
  main()

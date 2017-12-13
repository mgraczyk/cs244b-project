import os
import sys
import kazoo
import numpy as np
import time
import logging
import subprocess
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


def mkdirs_exists_ok(path):
  try:
    os.makedirs(path)
  except OSError:
    if not os.path.isdir(path):
      raise

def store_results(name, experiment_name, results):
  base_path = os.path.join('results', experiment_name)
  mkdirs_exists_ok(base_path)
  for kind, result in zip(('read', 'write', 'mixed'), results):
    np.savetxt(
        '{}/{}.{}.csv'.format(base_path, name, kind),
        result,
        delimiter=',')


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
    try:
      result = get_func('/latency_test/node_{}'.format(r))
    except Exception:
      pass
    if w % 2 == 0:
      data = result[0][:-1] or b'x'
    else:
      data = result[0] + b'x'
    try:
      set_func('/latency_test/node_{}'.format(w), data)
    except Exception:
      pass
    after = now()
    mixed_latencies.append(after - before)
  print_latencies(mixed_latencies)
  print('')

  for proc in procs:
    proc.terminate()
  for proc in procs:
    proc.wait()

  return (read_latencies, write_latencies, mixed_latencies)

def main():
  if len(sys.argv) < 2:
    test = 'local'
  else:
    test = sys.argv[1]

  zoo1_public = '54.183.205.29'
  zoo2_public = '54.153.9.2'
  zoo3_public = '54.242.30.248'
  zoo4_public = '52.34.167.196'

  zoo1_private = '172.31.7.146'
  zoo2_private = '172.31.13.236'

  if test == 'local':
    zk_hosts = ['127.0.0.1:2181', '127.0.0.1:2182', '127.0.0.1:2183']
    safari_hosts = ['127.0.0.1:12000', '127.0.0.1:12001', '127.0.0.1:12002']
  elif test == 'local_one':
    zk_hosts = ['127.0.0.1:2181']
    safari_hosts = ['127.0.0.1:12000']
  elif test == 'exp1':
    # Client is on zoo1
    zoo1 = zoo1_private
    zoo2 = zoo2_private
    zoo3 = zoo3_public
    zk_hosts = [
        '{}:2181'.format(zoo1), '{}:2181'.format(zoo2), '{}:2181'.format(zoo3)
    ]
    safari_hosts = [
        '{}:12000'.format(zoo1), '{}:12000'.format(zoo2),
        '{}:12000'.format(zoo3)
    ]
  elif test == 'exp2':
    # Client is on zoo1
    zoo4 = zoo4_public
    zoo2 = zoo2_private
    zoo3 = zoo3_public
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
  zk_results = test_latency(KazooClient, zk_hosts)
  store_results('zookeeper', test, zk_results)
  print('')

  print('Testing Safari latency')
  sf_results = test_latency(SafariClient, safari_hosts)
  store_results('safari', test, sf_results)
  print('')


if __name__ == '__main__':
  main()

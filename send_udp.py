import time
from socket import *

from safari.client import SafariClient

from benchmark import print_latencies

# client = SafariClient(["127.0.0.1:12000", "127.0.0.1:12001", "127.0.0.1:12002"])
client = SafariClient(["127.0.0.1:12000"])


client.ensure_path('/test')
s = client.set('/test', b'happy')
print(s)
d = client.get('/test')
print(d)
exit()

message = b'x' * 100
now = time.time

latencies = []
for _ in range(10000):
  try:
    start = now()
    response = client.ping(message)
    end = now()
    latencies.append(end - start)
  except timeout:
    print('REQUEST TIMED OUT')

print(response)
print_latencies(latencies)

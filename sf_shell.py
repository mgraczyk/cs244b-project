import time

from safari.client import SafariClient
from benchmark import print_latencies

sf_one = SafariClient(["127.0.0.1:12000"])
sf = SafariClient(["127.0.0.1:12000", "127.0.0.1:12001", "127.0.0.1:12002"])

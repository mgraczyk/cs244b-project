import sys
import os
import numpy as np
from matplotlib import pyplot as plt
import seaborn as sns
from matplotlib.backends.backend_pdf import PdfPages

def _load_data(experiment_name, name):
  base_path = os.path.join('results', experiment_name, name)
  read_latencies = 1000 * np.loadtxt('{}.{}.csv'.format(base_path, 'read'))
  write_latencies = 1000 * np.loadtxt('{}.{}.csv'.format(base_path,'write'))
  mixed_latencies = 1000 * np.loadtxt('{}.{}.csv'.format(base_path,'mixed'))
  return read_latencies, write_latencies, mixed_latencies


def _show_for_type(experiment_name, name, lims):
  read_latencies, write_latencies, mixed_latencies = _load_data(
      experiment_name, name)

  f, (ax1, ax2, ax3) = plt.subplots(3, sharex=True, sharey=False)
  for ax in (ax1, ax2, ax3):
    ax.set_xscale('log')
    ax.set_xlim(lims)

  sns.distplot(read_latencies, ax=ax1)
  sns.distplot(write_latencies, ax=ax2)
  sns.distplot(mixed_latencies, ax=ax3)

  ax1.set_ylabel('Read')
  ax2.set_ylabel('Write')
  ax3.set_ylabel('Mixed')

  f.subplots_adjust(hspace=0)
  plt.setp([a.get_xticklabels() for a in f.axes[:-1]], visible=False)
  ax3.set_xlabel('time (ms)')
  return f

if __name__ == '__main__':
  experiment_name = 'local'
  zk_fig = _show_for_type('local', 'zookeeper', [5e-2, 5e1])
  with PdfPages('results/local/zookeeper.pdf'.format(experiment_name)) as pp:
    pp.savefig(zk_fig)

  sf_fig = _show_for_type('local', 'safari', [5e-2, 5e1])
  with PdfPages('results/local/safari.pdf'.format(experiment_name)) as pp:
    pp.savefig(sf_fig)

  zk_fig = _show_for_type('exp1', 'zookeeper', [8e-2, 2e2])
  with PdfPages('results/exp1/zookeeper.pdf'.format(experiment_name)) as pp:
    pp.savefig(zk_fig)

  sf_fig = _show_for_type('exp1', 'safari', [8e-2, 2e2])
  with PdfPages('results/exp1/safari.pdf'.format(experiment_name)) as pp:
    pp.savefig(sf_fig)

  zk_fig = _show_for_type('exp2', 'zookeeper', [2e1, 1.5e2])
  with PdfPages('results/exp2/zookeeper.pdf'.format(experiment_name)) as pp:
    pp.savefig(zk_fig)

  sf_fig = _show_for_type('exp2', 'safari', [2e1, 1.5e2])
  with PdfPages('results/exp2/safari.pdf'.format(experiment_name)) as pp:
    pp.savefig(sf_fig)

  # plt.show()

"""Report paired comparisons and order-averaged savings for the full factorial."""
from collections import defaultdict
from itertools import permutations
import json
from pathlib import Path
from statistics import mean
import sys


def analyze(samples):
    blocks = defaultdict(dict)
    for s in samples:
        key = s['series'], s['round']
        if s['mode'] in blocks[key]:
            raise ValueError(f'duplicate {key}: {s["mode"]}')
        blocks[key][s['mode']] = s['ns'] / 1e6
    modes = list(next(iter(blocks.values())))
    if not all(set(b) == set(modes) for b in blocks.values()):
        raise ValueError('incomplete block')
    rows = list(blocks.values())
    averages = {m: mean(b[m] for b in rows) for m in modes}
    delta = {m: [b['base'] - b[m] for b in rows] for m in modes}
    gap = averages['base'] - averages['iwasm']
    for m in modes:
        print(f'{m:10} {averages[m]:8.2f} ms   saved {mean(delta[m]):7.2f} ms'
              f'   {100 * mean(delta[m])/gap:5.1f}% of gap')
    if not {'D', 'R', 'M', 'DR', 'DM', 'RM', 'DRM'} <= set(modes):
        return
    orders = list(permutations('DRM'))
    for factor in 'DRM':
        def marginal(block, order):
            index = order.index(factor)
            before = ''.join(c for c in 'DRM' if c in order[:index]) or 'base'
            after = ''.join(c for c in 'DRM' if c in order[:index+1])
            return block[before] - block[after]
        contributions = {series: mean(marginal(b, order) for (s, _), b in blocks.items()
                                      if s == series for order in orders)
                         for series in {i[0] for i in blocks}}
        amounts = [mean(marginal(b, order) for b in rows) for order in orders]
        print(f'{factor}: mean over orders {mean(amounts):.2f} ms'
              f' ({100*mean(amounts)/gap:.1f}% of gap); range {min(amounts):.2f}..{max(amounts):.2f} ms;'
              f' series {[round(v,2) for v in contributions.values()]}')


if __name__ == '__main__':
    analyze(json.loads(Path(sys.argv[1]).read_text())['samples'])

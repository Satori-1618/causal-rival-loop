"""Outcome-free, equal-budget selection policies for the development benchmark.

These are explicit experimental-design objectives, not new identification theorems.
Every selector receives the same public prediction/uncertainty information.
"""
from itertools import combinations
from statistics import NormalDist
import math
import random

import numpy as np

POLICIES = ('maximin', 'mean_pairwise', 'balanced_split', 'random', 'full_only')


def radii(sigmas, counts, alpha, numerical_bound):
    if not 0 < alpha < 1 or not math.isfinite(numerical_bound) or numerical_bound < 0:
        raise ValueError('Invalid alpha or numerical bound')
    sigma = np.asarray(sigmas, dtype=float)
    raw_counts = np.asarray(counts, dtype=float)
    if not np.isfinite(raw_counts).all() or np.any(raw_counts != np.floor(raw_counts)):
        raise ValueError('Counts must be finite integers')
    counts = raw_counts.astype(int)
    if (sigma.ndim != 1 or len(sigma) == 0 or counts.shape != sigma.shape
            or not np.isfinite(sigma).all() or np.any(sigma <= 0) or np.any(counts < 1)):
        raise ValueError('Finite positive known sigmas and integer counts required')
    z = NormalDist().inv_cdf(1 - alpha / (2 * len(sigma)))
    return z * sigma / np.sqrt(counts) + numerical_bound


def pair_gaps(predictions, equivalence_groups):
    """One row per distinct FULL-MENU class pair; aliases cannot overweight a class."""
    names = set(predictions)
    groups = [list(g) for g in equivalence_groups]
    flat = [n for g in groups for n in g]
    if set(flat) != names or len(flat) != len(names) or any(not g for g in groups):
        raise ValueError('Equivalence groups must partition the candidates')
    table = np.asarray([predictions[g[0]] for g in groups], dtype=float)
    if table.ndim != 2 or not np.isfinite(table).all() or len(table) < 2:
        raise ValueError('Need complete finite predictions and at least two classes')
    for g in groups:
        if any(list(predictions[n]) != list(predictions[g[0]]) for n in g):
            raise ValueError('Declared aliases disagree on the full menu')
    return np.asarray([np.abs(table[i] - table[j])
                       for i, j in combinations(range(len(groups)), 2)])


def split_order(menu, mandatory_count):
    desired = [f'read_{channel}:c{context}:d{dose}'
               for dose in ('1', '0.5', '2')
               for context in (0, 1) for channel in ('a', 'b')]
    indices = [menu.index(name) for name in desired if name in menu]
    if set(indices) != set(range(mandatory_count, len(menu))):
        raise ValueError('Fixed read-split schedule does not cover this menu')
    return indices


def select(predictions, equivalence_groups, menu, sigmas, numerical_bound, *,
           mandatory_count, extras, samples=8, alpha=0.005, seed=0):
    """Return plans and pre-outcome separation diagnostics; no truth/data argument.

    Exhaustive search is practical for this small menu. Stable menu order resolves
    ties after the declared secondary objective. It is not an oracle over outcomes.
    """
    width = len(menu)
    if (len(set(menu)) != width or not 0 < mandatory_count < width
            or not 0 <= extras <= width - mandatory_count or samples < 1
            or int(samples) != samples):
        raise ValueError('Invalid menu/budget')
    gap = pair_gaps(predictions, equivalence_groups)
    if gap.shape[1] != width:
        raise ValueError('Menu and predictions disagree')
    counts = np.full(width, samples, dtype=int)
    radius = radii(sigmas, counts, alpha, numerical_bound)
    standardized = gap / (2 * radius[None, :])
    se = np.asarray(sigmas, dtype=float) / math.sqrt(samples)
    mean_information = np.mean((gap / se[None, :]) ** 2, axis=0)
    base = list(range(mandatory_count))
    options = list(combinations(range(mandatory_count, width), extras))
    choices = []
    for extra in options:
        indices = base + list(extra)
        pair_separation = standardized[:, indices].max(axis=1)
        # Capping only the tiebreaker prevents an already easy pair dominating it.
        score = (float(pair_separation.min()),
                 float(np.minimum(pair_separation, 1).mean()))
        choices.append((extra, score))
    best, best_score = max(choices, key=lambda item: item[1])
    mean_best = max(options, key=lambda indices: sum(mean_information[j] for j in indices))
    selected = {
        'maximin': base + list(best),
        'mean_pairwise': base + list(mean_best),
        'balanced_split': base + split_order(menu, mandatory_count)[:extras],
        'random': base + sorted(random.Random(seed).sample(list(range(mandatory_count, width)), extras)),
        'full_menu': list(range(width)),
    }
    plans = {}
    for policy, indices in selected.items():
        plans[policy] = {'cells': indices, 'counts': [samples] * len(indices),
                         'cost': samples * len(indices)}
    total = samples * (mandatory_count + extras)
    quotient, remainder = divmod(total, mandatory_count)
    plans['full_only'] = {'cells': base,
                          'counts': [quotient + int(j < remainder) for j in base],
                          'cost': total}
    return {'plans': plans, 'maximin_score': best_score[0],
            'maximin_tiebreak': best_score[1], 'subsets_examined': len(options),
            'radius': radius.tolist()}

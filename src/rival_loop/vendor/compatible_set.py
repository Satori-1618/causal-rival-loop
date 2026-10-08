"""The inference rule: after the run, keep every explanation the data cannot exclude.

A candidate is compatible when its prediction lies within the declared radius of the
estimate in every cell. A declared equivalence group is decided once, as a group: it is
compared against the widest radius any member has, and it is retained if any member is
compatible under that radius. A group is therefore never split, however close its
members' predictions or radii are.

The result is one of four outcomes, always reported with the retained set:

  resolved                exactly one group retained
  partially_resolved      more than one group retained, but not all
  no_candidate_fits       nothing retained: the declared set does not contain the answer
  insufficient_evidence   everything retained: this run does not discriminate

Numerical or intervention failures are not outcomes of this rule. They keep their own
stated reason and must never be merged with a scientific null. A non-finite prediction,
estimate or radius is therefore refused with an error rather than classified.

The rule is only as good as the radius it is given. The radius must come from an
interval whose coverage holds at the sample size actually used: normal intervals built
from a sample SD over-exclude on small samples of discrete readouts, and there an exact
test is the safer source.
"""
import math

OUTCOMES = ('resolved', 'partially_resolved', 'no_candidate_fits',
            'insufficient_evidence')


def _cells(value, what):
    cells = (float(value),) if isinstance(value, (int, float)) else tuple(float(v) for v in value)
    if not all(math.isfinite(v) for v in cells):
        raise ValueError(f'{what} must be finite; a non-finite value is a failed measurement, '
                         f'not evidence against any candidate')
    return cells


def groups_of(names, equivalence_groups=()):
    """Disjoint groups over ``names``, singletons included, in a stable order."""
    names = list(names)
    seen, groups = set(), []
    for group in equivalence_groups:
        members = [m for m in group if m in names]
        unknown = set(group) - set(names)
        if unknown:
            raise ValueError(f'unknown candidates in an equivalence group: {sorted(unknown)}')
        if seen & set(members):
            raise ValueError('a candidate may belong to one equivalence group only')
        if members:
            groups.append(sorted(members))
            seen.update(members)
    groups.extend([name] for name in sorted(names) if name not in seen)
    return groups


def classify(groups, kept_groups):
    """One of the four outcomes, from all declared groups and the groups retained."""
    if not kept_groups:
        return 'no_candidate_fits'
    if len(kept_groups) == len(groups):
        return 'insufficient_evidence'
    if len(kept_groups) == 1:
        return 'resolved'
    return 'partially_resolved'


def compatible_set(predictions, estimate, radius, equivalence_groups=()):
    """Retain every declared group the estimate does not exclude.

    ``predictions`` maps each candidate to a number or a sequence, one entry per cell.
    ``estimate`` has the same shape. ``radius`` is a number, a sequence per cell, or a
    mapping from candidate to either; it is the half-width the analyst declared for the
    comparison (statistical, numerical, or their combination).
    """
    if not predictions:
        raise ValueError('no candidates declared: an empty set is a declaration error, '
                         'not a scientific outcome')
    est = _cells(estimate, 'estimate')
    pred = {name: _cells(value, f'prediction {name!r}') for name, value in predictions.items()}
    if isinstance(radius, dict):
        missing = set(pred) - set(radius)
        if missing:
            raise ValueError(f'no radius declared for {sorted(missing)}')
    for name, value in pred.items():
        if len(value) != len(est):
            raise ValueError(f'{name!r} predicts {len(value)} cells, estimate has {len(est)}')

    def radius_of(name):
        value = radius[name] if isinstance(radius, dict) else radius
        cells = _cells(value, f'radius for {name!r}')
        if len(cells) == 1 and len(est) > 1:
            cells = cells * len(est)
        if len(cells) != len(est) or any(r < 0 for r in cells):
            raise ValueError(f'invalid radius for {name!r}')
        return cells

    radii = {name: radius_of(name) for name in pred}
    groups = groups_of(pred, equivalence_groups)
    kept_groups, residuals = [], {}
    for members in groups:
        widest = tuple(max(cells) for cells in zip(*(radii[m] for m in members)))
        for m in members:
            residuals[m] = tuple(e - p for e, p in zip(est, pred[m]))
        if any(all(abs(r) <= w for r, w in zip(residuals[m], widest)) for m in members):
            kept_groups.append(members)
    return {'retained': sorted(m for g in kept_groups for m in g),
            'retained_groups': kept_groups, 'groups': groups,
            'outcome': classify(groups, kept_groups), 'residuals': residuals}

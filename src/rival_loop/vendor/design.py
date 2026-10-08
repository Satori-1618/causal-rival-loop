"""Step 2, before the run: which candidates can this design tell apart at all?

``signatures`` groups candidates whose predictions are *identical* in every cell of the
design. Two candidates with the same signature cannot be separated by any outcome of this
design, however precisely it is measured: that is structural equivalence, and it is exact.
``gains`` shows which pairs a set of extra cells would separate, so the cells can be chosen
before anything runs.

``groups_within`` is something else: a summary that chains candidates whose predictions
lie within a chosen tolerance. It can be a useful conservative flag ("these may be hard to
separate at this resolution"), but it proves no equivalence. With tolerance 0.1 it joins
0, 0.09 and 0.18, although the first and last differ by more than the tolerance.

Every prediction table must be complete and finite: each candidate predicts the same
cells, and a non-finite prediction is refused rather than grouped.
"""
import math


def _table(predictions):
    if not predictions:
        raise ValueError('no candidates declared')
    rows, width = {}, None
    for name, values in predictions.items():
        row = tuple(float(v) for v in values)
        if not all(math.isfinite(v) for v in row):
            raise ValueError(f'candidate {name!r} has a non-finite prediction')
        if width is None:
            width = len(row)
        elif len(row) != width:
            raise ValueError(f'candidate {name!r} predicts {len(row)} cells, others {width}')
        rows[name] = row
    return rows


def _pair(a, b):
    a, b = tuple(float(v) for v in a), tuple(float(v) for v in b)
    if len(a) != len(b):
        raise ValueError('prediction rows must cover the same cells')
    if not all(math.isfinite(v) for v in a + b):
        raise ValueError('non-finite prediction')
    return a, b


def restrict(predictions, cells):
    """The prediction table on a subset of cell indices."""
    rows = _table(predictions)
    width = len(next(iter(rows.values())))
    cells = list(cells)
    if any(not 0 <= i < width for i in cells):
        raise ValueError('cell index out of range')
    return {name: tuple(row[i] for i in cells) for name, row in rows.items()}


def signatures(predictions):
    """Candidates grouped by identical prediction rows: exact structural equivalence."""
    rows, groups = _table(predictions), {}
    for name in sorted(rows):
        groups.setdefault(rows[name], []).append(name)
    return sorted(groups.values())


def groups_within(predictions, tolerance):
    """Candidates chained together when some sequence links them, each step within
    ``tolerance`` in every cell. A conservative summary, not a proof of equivalence."""
    if not (math.isfinite(tolerance) and tolerance >= 0):
        raise ValueError('tolerance must be finite and non-negative')
    rows = _table(predictions)
    names = sorted(rows)
    parent = {n: n for n in names}

    def find(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if all(abs(x - y) <= tolerance for x, y in zip(rows[a], rows[b])):
                parent[find(b)] = find(a)
    groups = {}
    for n in names:
        groups.setdefault(find(n), []).append(n)
    return sorted(groups.values())


def separating_cells(a, b, tolerance=0.0):
    """Indices of the cells in which two prediction rows differ by more than the tolerance."""
    a, b = _pair(a, b)
    return [i for i, (x, y) in enumerate(zip(a, b)) if abs(x - y) > tolerance]


def gains(predictions, base_cells, extra_cells):
    """Pairs that share a signature on ``base_cells`` and are separated once
    ``extra_cells`` are added."""
    before = signatures(restrict(predictions, base_cells))
    after = signatures(restrict(predictions, list(base_cells) + list(extra_cells)))
    together_after = {frozenset((a, b)) for g in after for a in g for b in g if a < b}
    return sorted(tuple(sorted(pair)) for g in before for pair in
                  ({frozenset((a, b)) for a in g for b in g if a < b} - together_after))

"""Charts: turning query results into a picture saved under output/charts/.

One function, save_chart(), called by the `make_chart` tool in tools.py. The
tool hands it labels and values that came straight out of a SQL result - the
model chooses WHAT to plot, but never types the numbers itself.
"""

from __future__ import annotations

import re
from pathlib import Path

from services.config import get_settings

MAX_POINTS = 30


def chart_filename(title: str) -> str:
    """A safe file name derived from the chart title.  (PROVIDED)"""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]
    return f"{slug or 'chart'}.png"


def save_chart(labels: list[str], values: list[float], title: str,
               x_label: str = "", y_label: str = "", kind: str = "bar",
               out_dir: Path | str | None = None) -> Path:
    """Draw a bar or line chart and save it as a PNG.

    Args:
        labels: one label per point (x axis).
        values: one number per point (y axis); same length as `labels`.
        title: chart title; also determines the file name (see chart_filename).
        x_label, y_label: axis captions.
        kind: "bar" or "line".
        out_dir: target folder; defaults to output/charts. Created if missing.

    Returns:
        The path of the PNG that was written.

    Raises:
        ValueError: no points, more than MAX_POINTS points, labels and values
            of different lengths, or an unknown `kind`.
    """
    if kind not in ("bar", "line"):
        raise ValueError(f"kind must be 'bar' or 'line', not {kind!r}")
    if len(labels) != len(values):
        raise ValueError(f"{len(labels)} labels but {len(values)} values")
    if not labels:
        raise ValueError("nothing to plot")
    if len(labels) > MAX_POINTS:
        raise ValueError(f"too many points to plot ({len(labels)}); aggregate to at most {MAX_POINTS}")

    out_dir = Path(out_dir) if out_dir else get_settings().charts_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / chart_filename(title)

    # TODO M7-1 ─────────────────────────────────────────────────────────
    # Draw the chart and save it to `path`.
    #
    # Use matplotlib's object-oriented API, NOT pyplot:
    #
    #     from matplotlib.figure import Figure
    #     fig = Figure(figsize=(8, 4.5), dpi=120)
    #     ax = fig.subplots()
    #     ax.bar(labels, values)          # or ax.plot(labels, values, marker="o")
    #     ...
    #     fig.savefig(path)
    #
    # pyplot keeps a global "current figure" and a global backend. This code
    # runs on a worker thread inside an agent, possibly while a notebook is
    # drawing something else; a private Figure object touches no shared state
    # and needs no display.
    #
    # A chart a reader can use has: the title, both axis labels, the value
    # written on (or above) each bar, and x labels that do not overlap - rotate
    # them when there are many (ax.tick_params(axis="x", rotation=45)).
    # Call fig.tight_layout() before saving so nothing is cut off.
    raise NotImplementedError("TODO M7-1 (agent/charts.py)")

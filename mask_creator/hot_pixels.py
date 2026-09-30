"""Simple local-maximum hot pixel detector.

A "peak" is a pixel strictly brighter than every one of its (up to) 8
neighbours -- a fast, fully vectorised test that skips flat regions (dead
detector areas read as constant zero, for example) without any tie-breaking
logic.

For each peak we look at a small square window centred on it, split the
window into an "island" (pixels above the window's mean) and an "ocean"
(pixels at or below it), and flag the peak as a hot pixel when the island is
much brighter than the ocean.
"""

from __future__ import annotations

import numpy as np

# Size of the square window examined around each candidate peak. Not exposed
# in the GUI -- change here if a different neighbourhood is wanted.
WINDOW_SIZE = 5

# Successive "show more hot pixels" ratio thresholds (island mean / ocean
# mean). The first identification uses RATIO_LEVELS[0]; each press of "show
# more" steps to the next, lower, value. Not exposed in the GUI.
RATIO_LEVELS = (10, 5, 4, 3.5, 3, 2.5, 2, 1.5, 1.3)

# A peak's own pixel value must exceed this to be considered at all -- keeps
# the ratio test from firing on low-count noise. Not exposed in the GUI.
MIN_PEAK_VALUE = 1000


def find_peaks(image, min_value=MIN_PEAK_VALUE):
    """Return an (N, 2) array of (row, col) pixels that are local maxima.

    A pixel qualifies if it is strictly greater than all of its up-to-8
    immediate neighbours (border pixels compare only against the neighbours
    they actually have) and its value exceeds ``min_value``.
    """
    arr = np.asarray(image, dtype=np.float64)
    padded = np.full((arr.shape[0] + 2, arr.shape[1] + 2), -np.inf)
    padded[1:-1, 1:-1] = arr

    neighbor_max = np.full(arr.shape, -np.inf)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            window = padded[1 + dy:1 + dy + arr.shape[0], 1 + dx:1 + dx + arr.shape[1]]
            neighbor_max = np.maximum(neighbor_max, window)

    return np.argwhere((arr > neighbor_max) & (arr > min_value))


def hot_pixels_at_ratio(image, peaks, ratio, window_size=WINDOW_SIZE):
    """Filter ``peaks`` (as returned by :func:`find_peaks`) down to hot pixels.

    For each peak, the ``window_size``-square window centred on it is split
    at its own mean into an "island" (above the mean) and "ocean" (at or
    below it). A peak is a hot pixel when the island's mean exceeds ``ratio``
    times the ocean's mean.
    """
    arr = np.asarray(image, dtype=np.float64)
    half = window_size // 2
    height, width = arr.shape

    hits = []
    for r, c in peaks:
        r0, r1 = max(0, r - half), min(height, r + half + 1)
        c0, c1 = max(0, c - half), min(width, c + half + 1)
        window = arr[r0:r1, c0:c1]

        mean = window.mean()
        island = window[window > mean]
        ocean = window[window <= mean]
        if island.size == 0 or ocean.size == 0:
            continue

        island_mean = island.mean()
        ocean_mean = ocean.mean()
        is_hot = island_mean > ratio * ocean_mean if ocean_mean > 0 else island_mean > 0
        if is_hot:
            hits.append((int(r), int(c)))

    return hits

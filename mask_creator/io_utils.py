"""Reading detector images and reading/writing pixel masks.

Mask polarity
-------------
Everywhere inside this application a mask is a boolean array where
``True`` means *masked* (bad pixel, excluded from analysis).

On disk the beamline convention is the opposite, and is documented in
``CMS_SAXS/combineMask.m``::

    % mask value: 0 belongs mask; 1 belongs image

so a stored ``1``/white pixel is a *valid* pixel.  Conversion happens only in
this module; nothing else in the app needs to think about it.

Orientation
-----------
For h5 masks, row 0 of the image corresponds to row 0 of the mask array; no
vertical flip is applied on save or load, matching ``maskmake.m``
(savemask/loadmask) and ``qCalibration2.m`` (which reads masks with the
``imgUpsideDn`` variant commented out).

Bitmap masks are the exception: ``save_mask_bmp`` and ``load_mask`` take a
``flip_vertical`` flag, because the bitmaps in circulation were written by
tools that treat row 0 as the *bottom* row.  The app defaults it to on for
bmp/png/tif, and the user can switch it in the Output panel.
"""

from __future__ import annotations

import datetime
import re
import struct
from pathlib import Path

import numpy as np

# Detector files from 12-ID are written with external HDF5 compression
# filters -- LZ4 (32004) on the Pilatus/Eiger data, and bitshuffle or blosc
# elsewhere.  Those are not built into the conda-forge HDF5 build, so without
# a registered plugin any read fails with the opaque
# "Can't synchronously read data (can't open directory)".
#
# Importing hdf5plugin registers the bundled filter libraries directly, which
# means the app does not depend on HDF5_PLUGIN_PATH being set in whatever
# shell it happens to be launched from.  It must be imported before the first
# read; importing it before h5py keeps that unambiguous.
try:
    import hdf5plugin  # noqa: F401
except ImportError:  # pragma: no cover - only if the env is incomplete
    hdf5plugin = None

import h5py

# Dataset that carries the mask inside an h5 output file.
H5_MASK_DATASET = "valid_pixel_mask"

# Candidate image datasets, highest priority first.  The middle entry is a
# pattern rather than a literal name; see _resolve_dataset.
_INDEXED_DATA_RE = re.compile(r"^data_?\d{5,6}$")


class MaskIOError(Exception):
    """Raised for any recoverable problem reading or writing a file."""


# --------------------------------------------------------------------------
# h5 image input
# --------------------------------------------------------------------------

def _list_datasets(h5file):
    """Return every dataset path in the file, in visit order."""
    found = []
    h5file.visititems(
        lambda name, obj: found.append("/" + name)
        if isinstance(obj, h5py.Dataset)
        else None
    )
    return found


def _resolve_dataset(h5file):
    """Pick the image dataset by the documented priority order.

    1. ``/entry/data/data``
    2. ``/entry/data/data{idx:05d}`` (also accepts the Eiger ``data_000001``
       spelling); the lowest-numbered one wins
    3. ``/dp``
    """
    if "/entry/data/data" in h5file and isinstance(
        h5file["/entry/data/data"], h5py.Dataset
    ):
        return "/entry/data/data"

    group = h5file.get("/entry/data")
    if isinstance(group, h5py.Group):
        indexed = sorted(k for k in group.keys() if _INDEXED_DATA_RE.match(k))
        for key in indexed:
            if isinstance(group[key], h5py.Dataset):
                return "/entry/data/" + key

    if "/dp" in h5file and isinstance(h5file["/dp"], h5py.Dataset):
        return "/dp"

    available = _list_datasets(h5file)
    raise MaskIOError(
        "No image dataset found. Looked for /entry/data/data, "
        "/entry/data/data{idx:05d}, and /dp.\n\nDatasets in this file:\n  "
        + ("\n  ".join(available) if available else "(none)")
    )


# HDF5 filter ids we expect to meet, for a readable error message.
_FILTER_NAMES = {
    307: "bzip2",
    32000: "LZF",
    32001: "Blosc",
    32004: "LZ4",
    32008: "bitshuffle",
    32013: "ZFP",
    32015: "Zstandard",
}


def _filter_hint(dataset, name, exc):
    """Turn an opaque HDF5 read failure into something actionable.

    A missing compression filter surfaces as "can't open directory", which
    says nothing about the real cause.
    """
    try:
        plist = dataset.id.get_create_plist()
        filters = [plist.get_filter(i)[0] for i in range(plist.get_nfilters())]
    except Exception:  # pragma: no cover - diagnostics must never mask the error
        filters = []

    external = [f for f in filters if f not in (1, 2, 3)]  # deflate/shuffle/fletcher
    if not external:
        return f"Could not read {name!r}: {exc}"

    described = ", ".join(
        f"{_FILTER_NAMES.get(f, 'filter ' + str(f))} ({f})" for f in external
    )
    installed = "is installed" if hdf5plugin is not None else "is NOT installed"
    return (
        f"Could not read {name!r}: the dataset is compressed with {described}, "
        f"and HDF5 could not load that filter.\n\n"
        f"The hdf5plugin package {installed} in this environment.\n\n"
        "Fix with:\n"
        "    conda install -c conda-forge hdf5plugin\n\n"
        f"Underlying error: {exc}"
    )


def load_h5_image(path, dataset=None):
    """Load a detector image from an h5 file.

    Parameters
    ----------
    path : str or Path
    dataset : str, optional
        Explicit dataset path.  When ``None`` the priority order above is used.

    Returns
    -------
    (array, dataset_name)
        ``array`` is 2D or 3D (a stack of frames); it is returned as-is,
        without squeezing, so the caller can offer a frame selector.
    """
    path = Path(path)
    if not path.exists():
        raise MaskIOError(f"File not found: {path}")

    with h5py.File(path, "r") as f:
        name = dataset or _resolve_dataset(f)
        if name not in f:
            raise MaskIOError(f"Dataset {name!r} is not in {path.name}")
        node = f[name]
        if not isinstance(node, h5py.Dataset):
            raise MaskIOError(f"{name!r} is a group, not a dataset")
        try:
            data = node[()]
        except OSError as exc:
            raise MaskIOError(_filter_hint(node, name, exc)) from exc

    data = np.asarray(data)
    # Collapse length-1 leading axes, e.g. (1, 1679, 1475) -> (1679, 1475).
    while data.ndim > 2 and data.shape[0] == 1:
        data = data[0]
    if data.ndim not in (2, 3):
        raise MaskIOError(
            f"Dataset {name!r} has shape {data.shape}; expected a 2D image "
            "or a 3D stack of images."
        )
    return data, name


def project_stack(data, mode="frame", frame=0):
    """Reduce a possibly-3D image stack to the single 2D array to work on."""
    data = np.asarray(data)
    if data.ndim == 2:
        return data
    if mode == "sum":
        return data.sum(axis=0)
    if mode == "max":
        return data.max(axis=0)
    return data[int(np.clip(frame, 0, data.shape[0] - 1))]


class VarianceCancelled(Exception):
    """Raised by compute_pixelwise_variance when ``progress`` returns falsy."""


def compute_pixelwise_variance(paths, progress=None):
    """Pixel-wise variance across every frame found in ``paths``.

    Each path is loaded with :func:`load_h5_image`; a 2D result counts as one
    frame, a 3D result (stack) contributes one frame per entry along its
    first axis. Frames are accumulated with Welford's online algorithm, so
    peak memory is one file's data plus two image-sized accumulators --
    never a full stack of every frame across every file.

    Parameters
    ----------
    paths : sequence of str or Path
    progress : callable, optional
        Called as ``progress(index, total, path)`` after each *file* (not
        each frame) finishes, ``index`` starting at 1. If it returns a
        falsy value, :class:`VarianceCancelled` is raised.

    Returns
    -------
    (variance, n_frames)
    """
    paths = list(paths)
    mean = m2 = shape = None
    n = 0

    for i, path in enumerate(paths):
        try:
            data, name = load_h5_image(path)
        except (MaskIOError, OSError) as exc:
            raise MaskIOError(f"{Path(path).name}: {exc}") from exc

        frames = data[np.newaxis, ...] if data.ndim == 2 else data
        for frame in frames:
            frame = np.asarray(frame, dtype=np.float64)
            if shape is None:
                shape = frame.shape
                mean = np.zeros(shape, dtype=np.float64)
                m2 = np.zeros(shape, dtype=np.float64)
            elif frame.shape != shape:
                raise MaskIOError(
                    f"{Path(path).name}: dataset {name!r} has image shape "
                    f"{frame.shape}, which does not match the first file's "
                    f"shape {shape}."
                )
            n += 1
            delta = frame - mean
            mean += delta / n
            m2 += delta * (frame - mean)

        if progress is not None and not progress(i + 1, len(paths), path):
            raise VarianceCancelled()

    if n < 2:
        raise MaskIOError(
            "Need at least two images in total across the selected files to "
            "compute a variance."
        )
    return m2 / n, n


# --------------------------------------------------------------------------
# Mask input
# --------------------------------------------------------------------------

def _orient(mask, expected_shape):
    """Return ``mask`` shaped like ``expected_shape``, transposing if needed.

    Mirrors ``_orient_mask`` in APS12AzimAvg/processing/image.py.
    """
    if expected_shape is None or mask.shape == tuple(expected_shape):
        return mask
    if mask.T.shape == tuple(expected_shape):
        return mask.T
    raise MaskIOError(
        f"Mask shape {mask.shape} does not match the image shape "
        f"{tuple(expected_shape)} (and its transpose does not either)."
    )


def _load_mask_h5(path):
    with h5py.File(path, "r") as f:
        if H5_MASK_DATASET in f:
            valid = f[H5_MASK_DATASET][()]
        else:
            candidates = [
                n for n in _list_datasets(f) if np.asarray(f[n]).ndim == 2
            ]
            if not candidates:
                raise MaskIOError(
                    f"{Path(path).name} has no {H5_MASK_DATASET!r} dataset "
                    "and no 2D dataset to fall back on."
                )
            valid = f[candidates[0]][()]
    return np.asarray(valid)


def _load_mask_image(path):
    from PIL import Image

    with Image.open(path) as im:
        return np.asarray(im)


def load_mask(path, expected_shape=None, flip_vertical=False):
    """Load a mask from h5/bmp/png/tif.  Returns bool array, True = masked.

    ``flip_vertical`` reverses the row order after the mask has been brought
    into the image's orientation, so it means the same thing here as it does
    in :func:`save_mask_bmp`: load(save(m, flip)) == m.
    """
    path = Path(path)
    if not path.exists():
        raise MaskIOError(f"File not found: {path}")

    if path.suffix.lower() in (".h5", ".hdf5", ".nxs"):
        valid = _load_mask_h5(path)
    else:
        valid = _load_mask_image(path)

    valid = np.squeeze(np.asarray(valid))
    if valid.ndim == 3:
        # An RGB bitmap; any non-black pixel counts as valid.
        valid = valid.any(axis=2)
    if valid.ndim != 2:
        raise MaskIOError(f"Expected a 2D mask, got shape {valid.shape}")

    masked = valid == 0  # stored 0 = masked, nonzero = valid
    masked = _orient(masked, expected_shape)
    if flip_vertical:
        masked = masked[::-1]
    return masked


# --------------------------------------------------------------------------
# Mask output
# --------------------------------------------------------------------------

def save_mask_h5(path, masked):
    """Write ``valid_pixel_mask`` (uint8, 1 = valid) into an h5 file.

    Opens in append mode so a mask can be dropped alongside existing data;
    an existing ``valid_pixel_mask`` is replaced.
    """
    masked = np.asarray(masked, dtype=bool)
    valid = (~masked).astype(np.uint8)

    with h5py.File(path, "a") as f:
        if H5_MASK_DATASET in f:
            del f[H5_MASK_DATASET]
        dset = f.create_dataset(
            H5_MASK_DATASET, data=valid, compression="gzip", compression_opts=4
        )
        dset.attrs["description"] = "1 = valid pixel, 0 = masked pixel"
        dset.attrs["created_by"] = "mask_creator"
        dset.attrs["created"] = datetime.datetime.now().isoformat(timespec="seconds")


def save_mask_bmp(path, masked, flip_vertical=False):
    """Write a 1-bit BMP, white = valid, byte-compatible with the beamline files.

    Hand-rolled rather than going through Pillow so the header matches the
    existing masks exactly: BITMAPINFOHEADER, BI_RGB, bottom-up, no DPI
    fields, 2-entry black/white palette.

    With ``flip_vertical`` the rows are reversed before packing, so the image
    in the file is upside down relative to what the app displays.
    """
    masked = np.asarray(masked, dtype=bool)
    if masked.ndim != 2:
        raise MaskIOError(f"Expected a 2D mask, got shape {masked.shape}")
    if flip_vertical:
        masked = masked[::-1]

    height, width = masked.shape
    valid = (~masked).astype(np.uint8)

    # MSB-first bit packing, one row at a time, then pad to a 4-byte stride.
    packed = np.packbits(valid, axis=1)          # (height, ceil(width/8))
    stride = (packed.shape[1] + 3) // 4 * 4
    rows = np.zeros((height, stride), dtype=np.uint8)
    rows[:, : packed.shape[1]] = packed

    pixel_data = rows[::-1].tobytes()            # positive height => bottom-up

    palette = b"\x00\x00\x00\x00" + b"\xff\xff\xff\x00"
    offset = 14 + 40 + len(palette)
    file_size = offset + len(pixel_data)

    header = struct.pack("<2sIHHI", b"BM", file_size, 0, 0, offset)
    header += struct.pack(
        "<IiiHHIIiiII",
        40,                 # header size
        width,
        height,             # positive => rows stored bottom-up
        1,                  # planes
        1,                  # bits per pixel
        0,                  # BI_RGB, no compression
        len(pixel_data),
        0,                  # x pixels per metre (reference files leave this 0)
        0,                  # y pixels per metre
        2,                  # colours used
        0,                  # colours important
    )

    Path(path).write_bytes(header + palette + pixel_data)

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
Row 0 of the h5 image corresponds to row 0 of the mask array.  No vertical
flip is applied on save or load, matching ``maskmake.m`` (savemask/loadmask)
and ``qCalibration2.m`` (which reads masks with the ``imgUpsideDn`` variant
commented out).
"""

from __future__ import annotations

import datetime
import re
import struct
from pathlib import Path

import h5py
import numpy as np

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
        data = node[()]

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


def load_mask(path, expected_shape=None):
    """Load a mask from h5/bmp/png/tif.  Returns bool array, True = masked."""
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
    return _orient(masked, expected_shape)


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


def save_mask_bmp(path, masked):
    """Write a 1-bit BMP, white = valid, byte-compatible with the beamline files.

    Hand-rolled rather than going through Pillow so the header matches the
    existing masks exactly: BITMAPINFOHEADER, BI_RGB, bottom-up, no DPI
    fields, 2-entry black/white palette.
    """
    masked = np.asarray(masked, dtype=bool)
    if masked.ndim != 2:
        raise MaskIOError(f"Expected a 2D mask, got shape {masked.shape}")

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

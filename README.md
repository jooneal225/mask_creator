# Mask Creator

A PyQt5 + pyqtgraph GUI for building binary detector pixel masks from h5 images.

Load a detector image, paint over the bad regions with polygon / circle /
rectangle / brush / threshold tools, and save the result as either an h5
`valid_pixel_mask` dataset or a 1-bit bitmap that is byte-compatible with the
masks the beamline's MATLAB tooling already produces.

---

## Installation

```bash
conda env create -f environment.yml
conda activate mask_creator
```

Or equivalently, by hand:

```bash
conda create -n mask_creator python=3.11 -y
conda activate mask_creator
conda install -c conda-forge pyqt=5.15 pyqtgraph h5py hdf5plugin numpy pillow -y
```

### Compressed detector files

`hdf5plugin` is not optional. The 12-ID detector files are written with
external HDF5 compression filters — LZ4 (id 32004) on the Pilatus and Eiger
data — and those are **not** built into the conda-forge HDF5 build. Without a
registered filter, every read fails with the unhelpful

```
Can't synchronously read data (can't open directory)
```

`mask_creator/io_utils.py` imports `hdf5plugin` before h5py, which registers
the bundled filter libraries directly. That deliberately avoids depending on
the `HDF5_PLUGIN_PATH` environment variable, which on this machine points at
`matSAXS_12ID_Nov2025/CMS_SAXS/plugins` for MATLAB's benefit and is only
visible to shells started after it was set. If a filter is still missing, the
app now reports which one by name instead of the raw HDF5 message.

## Running

```bash
conda activate mask_creator
python run_mask_creator.py                      # empty, then browse for a file
python run_mask_creator.py path/to/image.h5     # open a file straight away
```

`python -m mask_creator` works the same way.

---

## Input

### Dataset resolution

The image dataset is located automatically, in this priority order:

1. `/entry/data/data`
2. `/entry/data/data{idx:05d}` — the lowest-numbered match wins; the Eiger
   `data_000001` spelling is accepted too
3. `/dp`

Leading length-1 axes are dropped, so a `(1, 1679, 1475)` dataset is treated as
a single `1679 x 1475` image. Type an explicit path into **Dataset** to
override the search. If nothing matches, the error lists every dataset in the
file.

### Image stacks

A genuinely 3D dataset reveals a **Display** selector — *Single frame*, *Sum
all frames*, or *Max projection* — plus a frame spinbox. Sum and max are
usually the quickest way to find dead pixels across a series. Whichever you
choose becomes the "original image" that the threshold tool reads.

### Log display

**Log** shows `log10` of the image, and is **on by default**. These frames have
a median of a few counts against a beam centre in the millions, so the linear
view is almost entirely black and the features you mask around are invisible.

Non-positive pixels are clamped up to the smallest positive value in the frame
rather than becoming `-inf`, which would break auto-levelling. This is a
display setting only: it never affects the mask or the threshold tool, both of
which work on the raw values.

---

## Mask conventions

### Polarity: `0 = masked, 1 = valid`

This matches the existing beamline tooling, which states it explicitly in
`CMS_SAXS/combineMask.m`:

```matlab
% mask value: 0 belongs mask; 1 belongs image
```

and implements it in `SAXSimagviewer/2Danalysis/maskmake.m`, where the mask
starts as `uint8(ones(...))` and "Add to the mask" ANDs in zeros.

| | h5 `valid_pixel_mask` | BMP |
|---|---|---|
| valid pixel | `1` | white |
| masked pixel | `0` | black |

Inside the application the sense is inverted — a pixel you add to the mask is
`True` — but that never reaches disk. All conversion happens in
`mask_creator/io_utils.py`.

### Orientation: no vertical flip

Row 0 of the h5 image is row 0 of the saved mask, in both directions. This
follows `maskmake.m` (`savemask`/`loadmask` round-trip unflipped) and
`qCalibration2.m`, which reads masks with `mask = double(imread(file));` and
has the `imgUpsideDn` variant commented out. Note that
`generateGoodPixelMap.m` *does* flip, but only to compensate for its own
`readHdf5` orientation; masks written by this tool are not affected.

### BMP format

`save_mask_bmp` writes the header by hand rather than going through Pillow,
which would add DPI fields. The output reproduces the existing masks exactly:

| field | value |
|---|---|
| header | 40-byte `BITMAPINFOHEADER` |
| bits per pixel | 1 |
| compression | 0 (`BI_RGB`) |
| height | positive, so rows are stored bottom-up |
| row stride | packed width padded to a 4-byte multiple |
| x/y pixels per metre | 0, 0 |
| colours used | 2 |
| palette | `00 00 00 00` (black), `ff ff ff 00` (white) |

Re-saving `maskver2.bmp` through this tool reproduces the original file
byte for byte.

---

## Tools

| Tool | Notes |
|---|---|
| **Polygon** | Click to place vertices, right-click to remove the last. **Complete Polygon** closes the loop into a shape you can drag and reshape by its handles. **Apply** closes it if still open and commits. Stays armed so you can draw several regions in a row. |
| **Circle** | A true circle — the ROI's aspect ratio is locked and it has a single radius handle, so it cannot be dragged into an ellipse. No rotate handle, which would mean nothing on a circle. **Apply** commits and leaves the shape in place, so it can be stamped repeatedly. |
| **Rectangle** | An outline with resize *and* rotate handles. **Apply** commits and leaves the shape in place. |
| **Paintbrush** | Click and drag to paint; the slider sets the diameter in image pixels and a ring previews it on the cursor. One stroke is one undo step. |
| **Apply Threshold** | Selects pixels of the original image with `min <= value <= max`. Defaults `-inf` / `-0.1` catch the negative sentinels Pilatus and Eiger write into module gaps and dead pixels. The dialog counts the affected pixels live before you commit. |

Every tool obeys the **ADD / REMOVE** switch, so the same controls that build
the mask also erase it.

Every tool also draws its outline in the current mask colour — the polygon's
line, vertex markers and rubber band, the circle and rectangle outlines, the
brush cursor ring, and the uncommitted brush-stroke preview — and follows it
live when you change that colour. A tool's preview therefore always matches
the overlay it is about to paint into.

### The graph

The overlay marks the pixels that are **excluded**: the ones that get dropped
when you multiply your data by `valid_pixel_mask`. The legend above the graph
says so, with a swatch tracking the overlay colour.

Scroll to zoom, right-drag to box-zoom, middle-drag to pan. While the
paintbrush is armed the left button paints instead of panning; everything else
still works, because `MaskViewBox` offers each event to the active tool first
and falls through to the default behaviour when the tool declines it.

Right-click for a **Mask** submenu: overlay opacity, overlay colour, show/hide,
invert, clear. The disabled **More tools** entry marks where niche tools will
go.

`Ctrl+Z` / `Ctrl+Y` undo and redo the last 30 operations. `Esc` disarms the
current tool.

### Remembered between sessions

`QSettings` (registry key `12ID/MaskCreator` on Windows) stores the window
geometry and the last h5 path you loaded.

The path is restored into the input box but **not** opened automatically, so
relaunching does not spend time reading a large stack you may not want — press
**Load Image** when you do. A path given on the command line overrides the
remembered one and loads straight away. The remembered path is written as soon
as a load succeeds, not only at exit, so an unclean shutdown does not lose it.

---

## Adding a tool later

Subclass `BaseTool` in `mask_creator/tools/base.py`, implement whichever of
`activate` / `deactivate` / `on_click` / `on_drag` / `on_hover` / `apply` /
`complete` you need, and build a boolean selection array that you hand to
`self.commit(selection)` — that routes it through the ADD/REMOVE switch and
the undo stack for you.

`mask_creator/rasterize.py` already turns polygons, ellipses, rotated ROIs and
polyline strokes into boolean arrays, so most shapes are a few lines.

Register the class in `TOOL_REGISTRY` (`mask_creator/tools/__init__.py`) and add
a button in `_build_tools_group`, or wire it into the context menu in
`_build_context_menu` for something niche.

---

## Layout

```
+-- I/O & Controls ------------+  [#] Masked pixels excluded from
| Input                        |      data reduction
|   path            [Browse]   |  +-- Graph -----------------------+
|   [Load Image]               |  | [Apply][Complete][Cancel]      |
|   Dataset:  auto             |  |                                |
|   Display:  frame / sum / max|  |      image + mask overlay      |
|   [x] Log (log10 of image)   |  |                                |
| Output                       |  |                                |
|   [Save HDF5] [Save BMP]     |  |                                |
|   [Load Existing Mask]       |  +--------------------------------+
| Add or Remove Pixels         |  |  histogram / levels            |
|   ( ADD )  ( REMOVE )        |  +--------------------------------+
| Tools                        |
|   [Polygon]   [Circle]       |
|   [Rectangle] [Paintbrush]   |
|   Brush size  ---o---  24 px |
|   [Apply Threshold...]       |
| Settings                     |
|   Mask opacity ---o---  [#]  |
|   [Undo] [Redo] [Clear Mask] |
|   masked: 247,578 px (10.0%) |
|                      [Help]  |
+------------------------------+
```

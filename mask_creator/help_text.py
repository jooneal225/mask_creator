"""Content for the Help dialog."""

HELP_HTML = """
<h2>Mask Creator</h2>
<p>Build a binary detector pixel mask on top of an image loaded from an h5 file.</p>

<h3>Input</h3>
<p><b>Browse / Load</b> reads an image from an h5 file. The dataset is found
automatically, in this order: <tt>/entry/data/data</tt>, then
<tt>/entry/data/data{idx:05d}</tt>, then <tt>/dp</tt>. Set <b>Dataset</b> to
override with an explicit path.</p>
<p>If the dataset is a 3D stack, <b>Display</b> chooses a single frame, the sum
of all frames, or a maximum projection. Sum and max are usually the best way to
spot dead pixels across a series. Whichever you pick is the "original image"
that the threshold tool works on.</p>
<p><b>Log</b> displays <tt>log10</tt> of the image. Non-positive pixels are
clamped to the smallest positive value so they still render. This affects the
display only &mdash; never the mask or the threshold tool.</p>

<h3>Add or Remove</h3>
<p>The <b>ADD</b> / <b>REMOVE</b> switch applies to every tool. In ADD the tools
put pixels into the mask; in REMOVE the same tools take them back out. The
paintbrush therefore doubles as an eraser.</p>

<h3>Tools</h3>
<dl>
<dt><b>Polygon</b></dt>
<dd>Click on the image to drop vertices. Right-click removes the last one.
<i>Complete Polygon</i> closes the loop and turns it into a shape you can drag
by its body or reshape by its handles. <i>Apply</i> closes the loop if it is
still open and commits the enclosed pixels. The tool stays armed afterwards so
you can draw several regions in a row.</dd>

<dt><b>Circle</b> and <b>Rectangle</b></dt>
<dd>Place an outline in the middle of the view. Drag the body to move it, the
corner handle to resize, and the handle on the right edge to rotate.
<i>Apply</i> commits and leaves the shape in place, so you can stamp the same
shape in several spots.</dd>

<dt><b>Paintbrush</b></dt>
<dd>Click and drag to paint. The slider next to the button sets the diameter in
image pixels, and a ring on the cursor previews it. Each stroke is one undo
step.</dd>

<dt><b>Apply Threshold</b></dt>
<dd>Selects every pixel of the original image with
<tt>min &le; value &le; max</tt>. The defaults, <tt>-inf</tt> and <tt>-0.1</tt>,
catch the negative sentinel values that Pilatus and Eiger detectors write into
module gaps and dead pixels. The dialog shows how many pixels the current
limits select before you commit.</dd>
</dl>

<h3>The graph</h3>
<p>Scroll to zoom, right-drag to zoom a box, and middle-drag to pan. While the
paintbrush is armed the left button paints instead of panning.</p>
<p>Right-click for a <b>Mask</b> submenu with the overlay opacity slider, the
overlay colour, show/hide, invert and clear. A disabled <b>More tools</b> entry
marks where additional niche tools will go.</p>
<p><b>Undo</b> / <b>Redo</b> (Ctrl+Z / Ctrl+Y) step back through the last 30
operations.</p>

<h3>Output</h3>
<p><b>Save HDF5</b> writes a <tt>valid_pixel_mask</tt> dataset as
<tt>uint8</tt>. <b>Save BMP</b> writes a 1-bit bitmap matching the format the
beamline's existing masks use.</p>
<p>In both formats the stored convention is <b>1 = valid pixel, 0 = masked</b>,
the same as <tt>maskmake.m</tt> and <tt>combineMask.m</tt>. In the BMP that
means masked pixels are black.</p>
<p><b>Load Existing Mask</b> reads either format back, plus png and tif, and
transposes automatically if that is what it takes to match the image.</p>
<p>Two orientation controls live in the <b>Tools</b> menu.
<b>Bitmap rows</b> sets how bmp/png/tif masks are oriented on disk relative to
the image shown here, and applies to both saving and loading. <i>Inverted</i>,
the default, flips the rows top-to-bottom, matching the bitmaps already in use
at the beamline; <i>Same as display</i> keeps row 0 of the h5 image as row 0 of
the mask. HDF5 masks are never flipped.</p>
<p><b>Flip mask vertically</b>, just below it, is a one-off action rather than
a setting: it mirrors the mask you currently have top-to-bottom, which fixes a
mask that came in upside down. It is a normal undo step.</p>

<h3>Settings</h3>
<p><b>Invert Mask</b> swaps masked and unmasked pixels everywhere &mdash; the
same as the right-click <b>Mask &rarr; Invert mask</b> entry.</p>
"""

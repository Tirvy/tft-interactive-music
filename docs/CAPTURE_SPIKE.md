# Capture spike

The capture spike answers the Milestone 0 question: can the desktop app
enumerate Windows display sources, preview one, and save a screenshot
that is usable as recognition input? It verifies the plumbing only. It
does not implement calibration, cropping, OCR, or live analysis.

## Method

The pipeline is deliberately split between Electron processes:

1. **Main process** calls `desktopCapturer.getSources()` with
   `types: ['screen', 'window']`, fetches thumbnails and window icons,
   and joins screen sources to `screen.getAllDisplays()` metadata
   (DIP size, scale factor, physical size, rotation).
2. **Preload** exposes the source list, source selection, frame save, and
   reveal operations through a typed `window.tft` bridge.
3. **Renderer** requests `navigator.mediaDevices.getDisplayMedia()`. The
   main process answers `setDisplayMediaRequestHandler` with the selected
   source and grants `display-capture` permission only to the trusted
   main window.
4. **Renderer** draws the current video frame to a canvas at
   `video.videoWidth × video.videoHeight`, encodes PNG with
   `canvas.toBlob`, and sends the bytes over IPC.
5. **Main process** validates the request with Zod, checks the PNG magic
   bytes, and writes the file with an exclusive create flag into the
   configured capture directory.

Writing files, validating payloads, and choosing the source all stay in
the main process. The renderer only draws and encodes.

## Display mapping

Windows screen sources on the test machine report `display_id: ""` and
use compact ids such as `screen:0:0`, so matching on `display_id` alone
left DPI metadata empty. `resolveDisplayForSource` now tries, in order:

1. the explicit `display_id`,
2. the display id embedded in a `screen:<id>:<n>` source id,
3. the numeric segment as an index into `screen.getAllDisplays()`,
4. the primary display when exactly one display exists.

This populates `displayScaleFactor`, `sourceWidth`, and `sourceHeight` on
screen sources so the spike can record DPI behavior.

## Automated verification

`pnpm --filter @tft/desktop smoke:capture` runs the same
`getDisplayMedia` → canvas → IPC save path from the renderer, using the
first screen source, then exits.

Last result (Windows 11, 2560×1600 display at 150% scaling):

| Field | Value |
| --- | --- |
| Source id | `screen:0:0` |
| Source name | `Весь экран` |
| Captured frame | 2560 × 1600 |
| `displayScaleFactor` | 1.5 |
| Derived `sourceWidth` × `sourceHeight` | 2561 × 1601 |
| PNG size | 2,185,088 bytes |
| Saved file | `%APPDATA%\TFT Soundtrack Companion\captures\tft-capture-…-source-83d885e5.png` |
| Exit code | 0 |

The captured frame matches the physical 2560×1600 panel. The derived
physical size is one pixel larger on each axis because Electron reports
display bounds in device-independent pixels and this code multiplies by
the scale factor and rounds. The captured frame is authoritative; the
derived size is diagnostic only.

## Manual checklist still required

The automated run covers one screen at one scale. Before Milestone 2,
verify by hand in the capture page:

- [ ] Capture the full TFT window and a full screen at 1080p.
- [ ] Repeat at 1440p and 4K.
- [ ] Repeat at Windows display scaling 100%, 125%, and 150%.
- [ ] Compare the reported video frame size with the display's physical
      size and the saved PNG dimensions.
- [ ] Confirm the saved PNG matches the live preview and is not
      letterboxed or cropped.
- [ ] Note whether window capture includes the game boundary, the Windows
      title bar, or overlays.
- [ ] Measure sustained frame rate over three seconds at the intended
      capture rate, and record the delivered rate.
- [ ] Confirm behavior with mixed-DPI multi-monitor setups and with the
      game on a secondary display.

## Known limitations

- Window capture excludes minimized or occluded content depending on the
  Windows compositor; the spike does not test this yet.
- `getDisplayMedia` frame rate is a constraint hint. The renderer records
  the track's reported frame rate and a measured rate; Windows may
  deliver less.
- The display-to-source mapping is heuristic. Multi-monitor setups should
  be re-verified, and a wrong index would mislabel DPI diagnostics, not
  change the captured pixels.
- Capture runs through the renderer, so a future worker-facing pipeline
  must still confirm that PNG bytes survive the IPC boundary unchanged
  at full resolution.
- No capture permission prompt is shown. The main process grants
  `display-capture` only to the trusted window and chooses the source
  itself.

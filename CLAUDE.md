# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the tool

```
python spectro_tool.py
```

Or double-click `run.bat` on Windows.

Install dependencies (first time only):
```
pip install astropy>=6.0 numpy>=2.0 matplotlib>=3.9 PyQt6>=6.7 scipy>=1.13
```
Or run `install.bat`.

There are no tests or linting configs in this project.

## Architecture

Everything lives in a single file: `spectro_tool.py` (~4950 lines). No packages, no modules.

The entry point is `if __name__ == "__main__": main()` at the end of the file.

### Key classes

| Class | Role |
|---|---|
| `FolderWatcher(QThread)` | Polls a directory for new `.fits`/`.fit` files every N ms; emits `new_file_found` signal |
| `ImageCanvas(FigureCanvas)` | Displays the 2D FITS spectrum image with draggable region boundary handles and rubber-band zoom |
| `SpectrumCanvas(FigureCanvas)` | Plots the hot-pixel-filtered peak ADU per column, sky background, and linearity limit |
| `AdvisoryPanel(QWidget)` | Computed advisory text: peak fill, SNR, noise regime, exposure suggestion, gain advice |
| `RegionControl(QWidget)` | Paired spinboxes for editing a target or background Y-range |
| `WelfordStats` | Per-column running mean/variance using Welford's numerically stable online algorithm |
| `FrameRecord` | Dataclass holding per-frame metrics (peak ADU, SNR, FWHM, centroid, inclusion state) |
| `SessionData` | Accumulates all `FrameRecord` entries and drives Welford statistics + persistence tracking |
| `SessionMetricsCanvas(FigureCanvas)` | Slit-quality metrics chart (flux, centroid, asymmetry, RMS) |
| `ConvergenceProfileCanvas(FigureCanvas)` | Running-mean spectrum with ±σ/√N confidence envelope |
| `SNRSparklineCanvas(FigureCanvas)` | Continuum SNR vs frame number sparkline |
| `FrameManagerPanel(QWidget)` | Sortable per-frame table with auto-flagging, inclusion toggles, and export |
| `SessionMonitorWidget(QWidget)` | Container for the Session Monitor tab; owns all session-display sub-panels |
| `WavelengthCalibration` | Dataclass for a polynomial calibration result (not yet exposed in UI) |
| `CalibrationTab(QWidget)` | Wavelength calibration workflow (code present, tab not added to UI — work in progress) |
| `LogbookWidget(QWidget)` | Auto-saving per-target text notepad; writes `logbook_<Target>.txt` in the watch folder |
| `MainWindow(QMainWindow)` | Orchestrates all panels; owns config, watcher, and all signal→slot wiring |

### Data flow

1. `FolderWatcher` detects a new FITS file → `MainWindow._load_file()` → `load_fits()` returns a dict with `data` (float32 array), FITS header fields, and camera metadata.
2. `MainWindow._refresh_all()` pushes data through `ImageCanvas.refresh()` and `SpectrumCanvas.refresh()`.
3. `SpectrumCanvas.refresh()` calls `extract_spectrum()`, computes the hot-pixel-filtered column max, and returns `(x, spec, bg, n_target)`.
4. `AdvisoryPanel.refresh_data()` consumes those results to compute and display the text advisories.
5. Each new frame also creates a `FrameRecord` and calls `SessionData.add_frame()`, which updates Welford statistics incrementally.
6. Any UI interaction (drag handles, spinboxes, checkboxes, slider) calls `save_config()` and triggers the appropriate refresh path.

### Config

`spectro_config.json` is written next to `spectro_tool.py` and is auto-saved on every UI change. `load_config()` merges stored values with `DEFAULTS` so missing keys are always back-filled. The `conversion_gain` and `read_noise` keys are overwritten automatically on each file load using the FITS `GAIN` header value looked up in `ASI585_TABLE`.

### Calibration tab (work in progress — not in UI)

`CalibrationTab` and its supporting classes (`CalibrationImageCanvas`, `CalibrationSpectrumCanvas`, `CalibrationResidualsCanvas`) exist in the source but the tab is **not added to the UI**. Do not expose it until it is complete.

The lamp line database (`LAMP_LINES`) supports: Ne glowlamp, NeXe (Philips S10), ArH (Osram ST111), NeArHe (Relco SC480).

## Camera-specific physics

**ZWO ASI 585MM Pro** — 12-bit native ADC, but FITS pixels are stored as 16-bit (raw 12-bit value × 16).  
All SNR math uses the 16-bit effective gain: `e_per_16bit_ADU = ZWO_published_value / 16`.

`ASI585_TABLE` contains measured (gain_slider, e_per_adu_16bit, read_noise_e, full_well_e) entries.  
`interp_gain(gain_slider)` interpolates within this table but **never interpolates across the HCG boundary at gain 200** — that boundary is a hard discontinuity in read noise (drops from ~4 e⁻ to ~1 e⁻).

SNR formula (per wavelength column):
```
signal_e = spectrum_ADU × G
noise_e  = sqrt(signal_e + N × (bg_per_row × G + R²))
SNR      = signal_e / noise_e
```
where G = conversion gain (e⁻/16-bit ADU), R = read noise (e⁻), N = number of TARGET rows.

## Night-vision palette

Two palettes are defined at module level: `NIGHT_PALETTE` (red-channel-only) and `DAY_PALETTE` (standard blue/grey). The active palette is mirrored into bare-name globals (`DARK_BG`, `TEXT`, `ACCENT`, etc.) by `_apply_palette_vars()`. `make_style()` regenerates the Qt stylesheet from these globals; call it and re-apply whenever the palette switches.

**Do not introduce green or blue UI elements** in night mode — all colours must be distinguishable by red-channel brightness only so the UI remains usable through a red astronomy filter.

When adding new UI widgets, register them in `_section_titles`, `_section_boxes`, `_section_seps`, or `_arrow_btns_list` if they need palette-aware recolouring on theme switch.

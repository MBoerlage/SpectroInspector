# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the tool

```
python spectro_tool.py
```

Or double-click `run.bat` on Windows.

Install dependencies (first time only):
```
pip install astropy numpy matplotlib PyQt6
```
Or run `install.bat`.

There are no tests or linting configs in this project.

## Architecture

Everything lives in a single file: `spectro_tool.py` (~2100 lines). No packages, no modules.

The file ends at line 1532 with `if __name__ == "__main__": main()`.

### Key classes

| Class | Role |
|---|---|
| `FolderWatcher(QThread)` | Polls a directory for new `.fits`/`.fit` files every N ms; emits `new_file_found` signal |
| `ImageCanvas(FigureCanvas)` | Displays the 2D FITS spectrum image with draggable region boundary handles and rubber-band zoom |
| `SpectrumCanvas(FigureCanvas)` | Plots the extracted 1D spectrum and optional SNR curve |
| `AdvisoryPanel(QWidget)` | Computed advisory text: peak fill, SNR, noise regime, exposure suggestion, gain advice |
| `RegionControl(QWidget)` | Paired spinboxes for editing a target or background Y-range |
| `MainWindow(QMainWindow)` | Orchestrates all panels; owns config, watcher, and all signal→slot wiring |

### Data flow

1. `FolderWatcher` detects a new FITS file → `MainWindow._load_file()` → `load_fits()` returns a dict with `data` (float32 array), FITS header fields, and camera metadata.
2. `MainWindow._refresh_all()` pushes the data through `ImageCanvas.refresh()` and `SpectrumCanvas.refresh()`.
3. `SpectrumCanvas.refresh()` calls `extract_spectrum()` and `compute_snr()`, returns `(x, spec, bg, n_target)`.
4. `AdvisoryPanel.refresh_data()` consumes those results to compute and display the text advisories.
5. Any UI interaction (drag handles, spinboxes, checkboxes, slider) calls `save_config()` and triggers the appropriate refresh path.

### Config

`spectro_config.json` is written next to `spectro_tool.py` and is auto-saved on every UI change. `load_config()` merges stored values with `DEFAULTS` so missing keys are always back-filled. The `conversion_gain` and `read_noise` keys are overwritten automatically on each file load using the FITS `GAIN` header value looked up in `ASI585_TABLE`.

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

All colours are defined in module-level constants (`DARK_BG`, `TEXT`, `ACCENT`, etc.) as hex strings. The entire UI is red-channel-only so it remains usable through a red astronomy filter. Do not introduce green or blue UI elements.

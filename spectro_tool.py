#!/usr/bin/env python3
"""
Spectro Exposure Time Tool  v4
Field FITS inspector for spectroscopy — StarEX 300 LR + ZWO ASI 585MM Pro.

Night-vision palette: all elements distinguished by RED-CHANNEL BRIGHTNESS only
(green/blue are invisible through a red astronomy filter).
"""

import sys
import math
import json
from pathlib import Path
from dataclasses import dataclass, field

import numpy as np

try:
    from astropy.io import fits as pyfits
except ImportError:
    print("ERROR: astropy not found.  Run:  pip install astropy"); sys.exit(1)

try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QSplitter,
        QVBoxLayout, QHBoxLayout, QGridLayout,
        QLabel, QPushButton, QRadioButton, QButtonGroup,
        QSpinBox, QDoubleSpinBox, QGroupBox, QSlider, QCheckBox,
        QFileDialog, QStatusBar, QSizePolicy, QFrame,
        QTabWidget, QTableWidget, QTableWidgetItem, QPlainTextEdit,
        QScrollArea,
    )
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QPoint, QTimer
    from PyQt6.QtGui import QPalette, QColor, QCursor, QFont
except ImportError:
    print("ERROR: PyQt6 not found.  Run:  pip install PyQt6"); sys.exit(1)

try:
    import matplotlib
    matplotlib.use("QtAgg")
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    from matplotlib.patches import Rectangle
    from matplotlib.ticker import FuncFormatter
except ImportError:
    print("ERROR: matplotlib not found.  Run:  pip install matplotlib"); sys.exit(1)

# ── Colour palettes ────────────────────────────────────────────────────────────
NIGHT_PALETTE = {
    "DARK_BG":    "#0a0000", "DARK_PANEL": "#150000",
    "DARK_BORDER":"#330800", "TEXT_DIM":   "#6b2200",
    "TEXT":       "#cc4400", "TEXT_HI":    "#ff6600",
    "ACCENT":     "#ffaa44", "WARN":       "#ff2200",
    "OK_COL":     "#ff9900", "TARGET_C":   "#ffaa44",
    "BG_C":       "#cc5533", "SAT_C":      "#ff2200",
    "SPEC_C":     "#ffaa44", "SNR_C":      "#ff7722",
    "RAW_C":      "#3a1100",
    "_BTN_BG":    "#1a0500", "_SEL_BG":    "#2a0a00",
}
DAY_PALETTE = {
    "DARK_BG":    "#f0f0f0", "DARK_PANEL": "#ffffff",
    "DARK_BORDER":"#ababab", "TEXT_DIM":   "#767676",
    "TEXT":       "#202020", "TEXT_HI":    "#000000",
    "ACCENT":     "#0078d4", "WARN":       "#c42b1c",
    "OK_COL":     "#107c10", "TARGET_C":   "#0078d4",
    "BG_C":       "#005a9e", "SAT_C":      "#c42b1c",
    "SPEC_C":     "#0078d4", "SNR_C":      "#00838f",
    "RAW_C":      "#e0e0e0",
    "_BTN_BG":    "#e1e1e1", "_SEL_BG":    "#cce4f7",
}

def _apply_palette_vars(pal: dict):
    global DARK_BG, DARK_PANEL, DARK_BORDER, TEXT_DIM, TEXT, TEXT_HI
    global ACCENT, WARN, OK_COL, TARGET_C, BG_C, SAT_C, SPEC_C, SNR_C, RAW_C
    global _is_day_mode
    _is_day_mode = (pal is DAY_PALETTE)
    DARK_BG=pal["DARK_BG"]; DARK_PANEL=pal["DARK_PANEL"]
    DARK_BORDER=pal["DARK_BORDER"]; TEXT_DIM=pal["TEXT_DIM"]
    TEXT=pal["TEXT"]; TEXT_HI=pal["TEXT_HI"]; ACCENT=pal["ACCENT"]
    WARN=pal["WARN"]; OK_COL=pal["OK_COL"]; TARGET_C=pal["TARGET_C"]
    BG_C=pal["BG_C"]; SAT_C=pal["SAT_C"]; SPEC_C=pal["SPEC_C"]
    SNR_C=pal["SNR_C"]; RAW_C=pal["RAW_C"]

_section_titles:       list = []   # title QLabels registered by section_box()
_section_boxes:        list = []   # QGroupBox instances registered by section_box()
_section_seps:         list = []   # separator QFrames registered by section_box()
_section_help_buttons: list = []   # HelpButton instances registered by section_box()
_cur_pal: dict = NIGHT_PALETTE   # mutable reference to active palette
_is_day_mode: bool = False

# initialise globals from night palette
DARK_BG=NIGHT_PALETTE["DARK_BG"]; DARK_PANEL=NIGHT_PALETTE["DARK_PANEL"]
DARK_BORDER=NIGHT_PALETTE["DARK_BORDER"]; TEXT_DIM=NIGHT_PALETTE["TEXT_DIM"]
TEXT=NIGHT_PALETTE["TEXT"]; TEXT_HI=NIGHT_PALETTE["TEXT_HI"]
ACCENT=NIGHT_PALETTE["ACCENT"]; WARN=NIGHT_PALETTE["WARN"]
OK_COL=NIGHT_PALETTE["OK_COL"]; TARGET_C=NIGHT_PALETTE["TARGET_C"]
BG_C=NIGHT_PALETTE["BG_C"]; SAT_C=NIGHT_PALETTE["SAT_C"]
SPEC_C=NIGHT_PALETTE["SPEC_C"]; SNR_C=NIGHT_PALETTE["SNR_C"]
RAW_C=NIGHT_PALETTE["RAW_C"]

# ── Font sizes (pt — DPI-independent) ─────────────────────────────────────────
F_BASE  = "12pt"   # labels, buttons, checkboxes, spinboxes
F_TITLE = "13pt"   # group/section titles
F_VAL   = "13pt"   # advisory values (bold)
F_SM    = "10pt"   # status bar, secondary text
F_HELP  = "10pt"   # help popup body

def make_style() -> str:
    if _is_day_mode:
        return ""   # let native Qt/Fusion render the standard Windows look
    return f"""
QMainWindow, QWidget   {{ background-color:{DARK_BG}; color:{TEXT}; font-size:{F_BASE}; }}
QGroupBox              {{ border:1px solid {DARK_BORDER}; border-radius:4px;
                          margin-top:10px; padding-top:4px; }}
QGroupBox::title       {{ subcontrol-origin:margin; left:8px;
                          color:{TEXT_HI}; font-size:{F_TITLE}; font-weight:bold; }}
QLabel                 {{ color:{TEXT}; font-size:{F_BASE}; }}
QPushButton            {{ background-color:{_cur_pal["_BTN_BG"]}; color:{TEXT_HI};
                          border:1px solid {DARK_BORDER}; border-radius:3px;
                          padding:5px 12px; font-size:{F_BASE}; }}
QPushButton:hover      {{ background-color:{DARK_PANEL}; }}
QPushButton:pressed    {{ background-color:{DARK_BORDER}; }}
QPushButton:checked    {{ background-color:{_cur_pal["_SEL_BG"]}; border:1px solid {ACCENT}; color:{ACCENT}; }}
QRadioButton           {{ color:{TEXT}; font-size:{F_BASE}; }}
QCheckBox              {{ color:{TEXT}; font-size:{F_BASE}; }}
QSpinBox, QDoubleSpinBox {{ background-color:{DARK_PANEL}; color:{ACCENT};
                          border:1px solid {DARK_BORDER}; border-radius:2px;
                          padding:3px; font-size:{F_BASE}; }}
QSlider::groove:horizontal {{ background:{DARK_BORDER}; height:5px; border-radius:2px; }}
QSlider::handle:horizontal {{ background:{ACCENT}; width:16px; height:16px;
                               margin:-6px 0; border-radius:8px; }}
QStatusBar             {{ background-color:{DARK_PANEL}; color:{TEXT_DIM};
                          font-size:{F_SM}; }}
QToolTip               {{ background-color:{DARK_PANEL}; color:{TEXT};
                          border:1px solid {DARK_BORDER}; font-size:{F_HELP}; }}
QScrollBar:vertical    {{ background:{DARK_PANEL}; width:10px; border:none; }}
QScrollBar::handle:vertical {{ background:{DARK_BORDER}; border-radius:4px; min-height:20px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
"""

STYLE = make_style()

# ── ASI585MM Pro gain lookup table ─────────────────────────────────────────────
# Measured data from ZWO spec sheet (latest firmware, HCG threshold = 200).
# Columns: (gain_slider, e_per_adu_16bit, read_noise_e, full_well_e)
#
# IMPORTANT: ZWO publishes e-/ADU for the 12-bit native ADC output.
# FITS files from ZWO cameras store 16-bit pixels (raw 12-bit value × 16).
# So the effective conversion gain for FITS pixel math = ZWO_value / 16.
# Example: gain 250, ZWO native = 0.35 e-/12-bit ADU → 0.35/16 = 0.022 e-/16-bit ADU.
#
# The HCG boundary at gain=200 is a hard discontinuity — do NOT interpolate
# read noise or full well linearly across it.
ASI585_TABLE = [
    # (gain_slider, e_per_adu_16bit, read_noise_e, full_well_e)
    (0,   0.594, 6.5, 40000),
    (50,  0.344, 5.5, 22000),
    (100, 0.188, 4.7, 11000),
    (150, 0.113, 4.1,  6000),
    (195, 0.063, 4.0,  4000),
    # ── HCG mode starts at gain 200 ──
    (200, 0.047, 1.0,  2500),
    (250, 0.022, 0.8,  1500),
    (300, 0.011, 0.7,  1000),
    (350, 0.006, 0.8,   700),
    (400, 0.003, 0.7,   300),
    (450, 0.001, 0.6,   150),
]
HCG_THRESHOLD = 200


def interp_gain(gain_slider: float) -> tuple[float, float, float]:
    """
    Interpolate (e_per_adu_16bit, read_noise_e, full_well_e) for a given gain slider.
    The HCG boundary at gain 200 is a hard discontinuity — the table is split
    into pre-HCG and HCG segments and interpolation never crosses the boundary.
    """
    g = float(gain_slider)
    pre  = [row for row in ASI585_TABLE if row[0] <  HCG_THRESHOLD]
    post = [row for row in ASI585_TABLE if row[0] >= HCG_THRESHOLD]

    if g < HCG_THRESHOLD:
        seg = pre
    else:
        seg = post

    if g <= seg[0][0]:
        return seg[0][1], seg[0][2], seg[0][3]
    if g >= seg[-1][0]:
        return seg[-1][1], seg[-1][2], seg[-1][3]
    for i in range(len(seg) - 1):
        g0, e0, rn0, fw0 = seg[i]
        g1, e1, rn1, fw1 = seg[i + 1]
        if g0 <= g <= g1:
            t = (g - g0) / (g1 - g0)
            return e0 + t*(e1-e0), rn0 + t*(rn1-rn0), fw0 + t*(fw1-fw0)
    return seg[-1][1], seg[-1][2], seg[-1][3]


# ── Help texts (HTML) ──────────────────────────────────────────────────────────
HELP = {

"image": """
<b>FITS Image Display</b><br><br>
The 2D spectrum from your spectrograph. The <b>X axis</b> (horizontal) maps to
wavelength — uncalibrated here, proportional to pixel column number.<br>
The <b>Y axis</b> (vertical) is the slit direction. Your star appears as a
bright horizontal band.<br><br>
<b>Red shaded column bands</b> = pixels above the saturation threshold
(default 70% of full ADU range). Those wavelength bins are clipped — reduce
exposure to remove them. The first band is labelled <b>SAT</b>.<br><br>
<b>Stretch slider</b>: applies arcsinh display stretch only — the raw FITS
data is never modified. Slide right to brighten faint continuum detail.<br><br>
<b>Zoom Box</b>: click the ⊕ button, then click-drag a rectangle on the image
to zoom in. The spectrum X-axis synchronises automatically. Click ↺ to reset.
""",

"regions": """
<b>Extraction Regions</b><br><br>
Three horizontal bands define how the 1D spectrum is extracted:<br><br>
• <b>TARGET</b> — rows containing the star. For each column (wavelength), all
pixel values in this range are summed.<br>
• <b>BG ABOVE / BG BELOW</b> — sky background rows on either side of the
star. Their row-average is subtracted from the target sum to remove sky
glow, light pollution, and detector offset.<br><br>
<b>To adjust</b>: drag the ▶ handles on the image, or type pixel row numbers
directly. Typical TARGET height is 20–60 rows depending on seeing and
slit alignment.
""",

"spectrum": """
<b>Extracted 1D Spectrum</b><br><br>
<b>X axis</b>: pixel column — proportional to wavelength (not calibrated).<br>
<b>Y axis</b>: intensity in ADU × rows (k = thousands, M = millions), or
normalised to peak = 1 if "Normalize" is checked.<br><br>
• <b>Amber line</b>: background-subtracted spectrum
  = Σ(target rows) − mean_bg_per_row × N_target_rows<br>
• <b>Dim line</b>: raw TARGET sum before subtraction<br>
• <b>Dashed red line</b>: saturation limit — the sum value if any pixel in
  the TARGET box reached the saturation threshold<br>
• <b>Red shading</b>: column runs where at least one TARGET pixel is saturated
""",

"snr": """
<b>Signal-to-Noise Ratio  (right axis, dotted line)</b><br><br>
SNR is calculated per wavelength column using the photon + sky + read-noise
model:<br><br>
&nbsp;&nbsp;signal_e = spectrum × G<br>
&nbsp;&nbsp;noise_e = √( signal_e + N × (bg_per_row × G + R²) )<br>
&nbsp;&nbsp;SNR = signal_e / noise_e<br><br>
where G = conversion gain (e⁻/16-bit ADU), R = read noise (e⁻),
N = number of TARGET rows.<br><br>
<b>Interpretation</b>: SNR 100 → 1% measurement uncertainty on a spectral
feature. Aim for SNR &gt; 50 for faint lines. Peak SNR is at the wavelength
of maximum stellar flux.<br><br>
<b>Important</b>: G is the 16-bit FITS gain (ZWO 12-bit native ÷ 16).
For ASI585MM Pro at gain 250: G ≈ 0.022 e⁻/ADU
(= 0.35 native 12-bit value ÷ 16 for FITS 16-bit container).
""",

"advisory": """
<b>Exposure Advisory</b><br><br>
<b>Peak fill</b>: highest pixel in the TARGET box as % of your saturation
threshold. Aim for 65–85%.<br><br>
<b>Frames → SNR 100</b>: estimated number of identical exposures to stack
to reach SNR 100 at the peak column, assuming background-limited √N scaling.
SNR_stack = SNR_single × √N_frames.<br><br>
<b>Noise regime</b>:<br>
• <i>Background-limited</i> — sky noise dominates; SNR ∝ √(exposure time).
  The most common case for spectroscopy of moderately bright stars.<br>
• <i>Read-noise limited</i> — detector read noise dominates; SNR ∝ t
  (linear). Typical for very faint targets or very short exposures.<br>
• <i>Signal-limited</i> — star photon noise dominates; SNR ∝ √t.<br><br>
<b>Exposure suggestion</b>: linear extrapolation to reach your target fill
(default 80%). Expected SNR gain assumes background-limited √t scaling.
""",

"fwhm": """
<b>Spatial FWHM Monitor</b><br><br>
Tracks the stellar trace width (in pixels) per frame as a real-time session KPI.<br><br>
<b>Pipeline</b>: For each frame the tool identifies <i>continuum columns</i> using the
flatness filter (derivative threshold), median-combines their spatial profiles,
then fits a Gaussian. FWHM = 2.355 × sigma.<br><br>
<b>Color coding</b>:<br>
• Orange (OK_COL) — within Warn% of session baseline<br>
• Bright orange (ACCENT) — between Warn% and Alarm% above baseline<br>
• Red — more than Alarm% above baseline, or Gaussian fit unreliable<br><br>
<b>Unreliable fits</b> (fit residuals too high) are plotted as dim points
and excluded from the baseline calculation.
""",

"convergence": """
<b>Signal Convergence Monitor</b><br><br>
Tracks signal accumulation as frames stack, using Welford's online algorithm.<br><br>
<b>Convergence chart</b>:<br>
• Solid amber line = running mean spectrum across all included frames<br>
• Shaded band = ±N×sigma confidence envelope; narrows visibly as N grows<br>
• Dimmed zones = columns excluded by flatness filter (spectral lines or edges)<br>
• Coloured tick marks below x-axis = columns where the persistence score
  exceeds the threshold — candidate real spectral features<br><br>
<b>SNR sparkline</b>: continuum SNR vs. included frame number. The dashed
reference line shows ideal √N growth. Significant deviation for 3+ consecutive
frames triggers a transparency/guiding warning.<br><br>
<b>Requires ≥ 3 included frames</b> before the envelope and persistence scores
are displayed.
""",

"sparkline": """
<b>Continuum SNR vs. Frame</b><br><br>
Tracks how continuum SNR grows as frames accumulate.<br><br>
• <b>Solid line</b> — actual continuum SNR per included frame<br>
• <b>Dashed line</b> — ideal √N growth reference from frame 1<br>
• <b>Target line</b> — optional SNR target (set SNR target spinner; 0 = off)<br><br>
If actual SNR deviates from √N reference for 3+ consecutive frames, a warning
is shown — possible transparency change, guiding loss, or exposure gap.<br><br>
<b>Requires ≥ 2 included frames</b> to plot.
""",

"gain": """
<b>Gain Advisory — ASI585MM Pro</b><br><br>
Based on measured ZWO curves (latest firmware). HCG mode activates at
gain slider >= 200.<br><br>
<b>HCG mode (gain >= 200)</b>:<br>
• Read noise drops from ~4 e⁻ to ~1 e⁻ — a 4× improvement<br>
• Full well: ~2 500 e⁻ at gain 200, falling steeply to ~150 e⁻ at gain 450<br>
• Gain 200 is the sweet spot: lowest RN with maximum full well in HCG<br><br>
<b>Normal mode (gain &lt; 200)</b>:<br>
• Read noise: 4–6.5 e⁻ (higher)<br>
• Full well: 4 000–40 000 e⁻ (much more dynamic range)<br><br>
<b>Decision guide</b>:<br>
• <i>Background-limited</i> → gain change barely affects SNR; use exposure time<br>
• <i>Read-noise limited</i> → jump to HCG (gain >= 200) for 4× RN improvement<br>
• <i>Saturating in HCG</i> → reduce exposure first; or drop to gain 100–150
  for 5–10× more full well (read noise rises to ~4.5 e⁻)<br>
• <i>Saturating below HCG</i> → reduce exposure only; already at max dynamic range
""",

}


# ── Help UI components ─────────────────────────────────────────────────────────
class HelpPopup(QFrame):
    """Floating dark panel with HTML text. Closes on any click or after 30 s."""

    def __init__(self, anchor: QWidget, html: str):
        super().__init__(anchor.window(),
                         Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {DARK_PANEL};
                border: 1px solid {DARK_BORDER};
                border-radius: 5px;
            }}
            QLabel {{ color:{TEXT}; font-size:{F_HELP};
                      background:transparent; border:none; }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        lbl = QLabel(html)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setWordWrap(True)
        lbl.setMaximumWidth(460)
        layout.addWidget(lbl)
        self.adjustSize()

        # Position below/right of anchor, clamped to screen
        gpos = anchor.mapToGlobal(QPoint(0, anchor.height() + 4))
        screen = QApplication.primaryScreen().availableGeometry()
        x = min(gpos.x(), screen.right()  - self.width()  - 8)
        y = min(gpos.y(), screen.bottom() - self.height() - 8)
        self.move(max(screen.left(), x), max(screen.top(), y))

        QTimer.singleShot(30000, self.close)

    def mousePressEvent(self, event):
        self.close()


class HelpButton(QLabel):
    """Small ⓘ label that opens a HelpPopup on left-click."""

    def __init__(self, html: str, parent=None):
        super().__init__("  ⓘ  ", parent)
        self._html = html
        self.setStyleSheet(f"color:{TEXT_HI}; font-size:12pt; border:none;")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setToolTip("Click for help")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            HelpPopup(self, self._html).show()
        super().mousePressEvent(event)


def section_box(title: str, help_key: str | None = None) -> tuple[QGroupBox, QVBoxLayout]:
    """Return a styled QGroupBox and its inner layout, with optional ⓘ button."""
    grp = QGroupBox()
    inner = QVBoxLayout(grp)
    inner.setContentsMargins(6, 4, 6, 6)
    inner.setSpacing(4)

    # Header row: title + help button
    header = QWidget()
    hl = QHBoxLayout(header)
    hl.setContentsMargins(0, 0, 0, 0)
    hl.setSpacing(2)
    tlbl = QLabel(title)
    tlbl.setStyleSheet(f"color:{TEXT_HI}; font-size:{F_TITLE}; font-weight:bold; border:none;")
    _section_titles.append(tlbl)
    hl.addWidget(tlbl)
    if help_key and help_key in HELP:
        hbtn = HelpButton(HELP[help_key])
        _section_help_buttons.append(hbtn)
        hl.addWidget(hbtn)
    hl.addStretch()
    inner.addWidget(header)

    # Thin separator
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet(f"QFrame{{background:{DARK_BORDER}; max-height:1px; border:none;}}")
    _section_seps.append(sep)
    inner.addWidget(sep)

    grp.setStyleSheet(f"""
        QGroupBox {{
            border: 1px solid {DARK_BORDER};
            border-radius: 4px;
            margin-top: 0px;
            padding-top: 2px;
        }}
    """)
    _section_boxes.append(grp)
    return grp, inner


# ── Config ─────────────────────────────────────────────────────────────────────
CONFIG_FILE = Path(__file__).with_name("spectro_config.json")

DEFAULTS: dict = {
    "watch_folder":         "",
    "target_y_start":       1000,
    "target_y_end":         1160,
    "bg_above_y_start":     880,
    "bg_above_y_end":       980,
    "bg_below_y_start":     1180,
    "bg_below_y_end":       1280,
    "saturation_threshold": 0.70,
    "target_fill":          0.80,
    "stretch_value":        3,
    "normalize_spectrum":   False,
    "show_snr":             True,
    "gain_advice_on":       False,
    # NOTE: ZWO FITS header GAIN = slider value (0–570), NOT e-/ADU.
    # conversion_gain = e_per_16bit_ADU for SNR math (ZWO 12-bit native / 16).
    # E.g. gain 250 → ZWO native 0.35 / 16 = 0.022 e-/16-bit ADU.
    "conversion_gain":      0.022,
    "read_noise":           0.8,
    "poll_interval_ms":     2000,
    # ── Session monitor ───────────────────────────────────────────────────
    "flatness_threshold":        500.0,
    "central_col_fraction":      0.35,
    "derivative_window":         7,
    "fwhm_warn_pct":             20.0,
    "fwhm_alarm_pct":            50.0,
    "gaussian_residual_thresh":  0.30,
    "envelope_sigma":            2.0,
    "persistence_threshold":     0.70,
    "snr_target":                0,
    "autoflag_snr_sigma":        2.0,
    "autoflag_fwhm_sigma":       2.0,
    "autoflag_snr_on":           True,
    "autoflag_fwhm_on":          True,
    "autoflag_sat_on":           True,
    "autoflag_continuum_on":     True,
}


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                cfg = json.load(f)
            for k, v in DEFAULTS.items():
                cfg.setdefault(k, v)
            return cfg
        except Exception:
            pass
    return dict(DEFAULTS)


def save_config(cfg: dict):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"Config save error: {e}")


# ── FITS loading ───────────────────────────────────────────────────────────────
def load_fits(filepath: str) -> dict | None:
    try:
        with pyfits.open(filepath) as hdul:
            data, header = None, None
            for hdu in hdul:
                if hdu.data is not None and hdu.data.ndim >= 2:
                    data, header = hdu.data, hdu.header
                    break
            if data is None:
                return None
            if data.ndim == 3:
                data = data[0]
            data = data.astype(np.float32)
            bitpix     = abs(int(header.get("BITPIX", 16)))
            full_range = float((1 << bitpix) - 1)
            data       = np.clip(data, 0, full_range)
            return {
                "data":        data,
                "bitpix":      bitpix,
                "full_range":  full_range,
                "exptime":     header.get("EXPTIME", header.get("EXPOSURE")),
                "gain_slider": header.get("GAIN",    header.get("EGAIN")),
                "camera":      header.get("INSTRUME", header.get("CAMERA", "Unknown")),
                "date_obs":    header.get("DATE-OBS", ""),
                "object":      header.get("OBJECT", ""),
                "filename":    Path(filepath).name,
                "filepath":    str(filepath),
            }
    except Exception as e:
        print(f"FITS load error: {e}")
        return None


# ── Folder watcher ─────────────────────────────────────────────────────────────
class FolderWatcher(QThread):
    new_file_found = pyqtSignal(str)

    def __init__(self, folder: str, interval_ms: int = 2000):
        super().__init__()
        self.folder = folder
        self.interval_ms = interval_ms
        self._running = True
        self._known: set[str] = set()
        self._latest: str | None = None
        self._scan_existing()

    def _glob(self) -> list[Path]:
        p = Path(self.folder)
        files: list[Path] = []
        if p.exists():
            for pat in ("*.fits", "*.fit", "*.FITS", "*.FIT"):
                files.extend(p.glob(pat))
        return files

    def _scan_existing(self):
        files = self._glob()
        self._known = {str(f) for f in files}
        if files:
            self._latest = str(max(files, key=lambda f: f.stat().st_mtime))

    def run(self):
        while self._running:
            self.msleep(self.interval_ms)
            if not self._running:
                break
            files   = self._glob()
            current = {str(f) for f in files}
            new     = current - self._known
            self._known = current
            if new:
                newest       = max(new, key=lambda f: Path(f).stat().st_mtime)
                self._latest = newest
                self.new_file_found.emit(newest)

    def stop(self):
        self._running = False

    def latest(self) -> str | None:
        return self._latest

    def count(self) -> int:
        return len(self._known)


# ── Math helpers ───────────────────────────────────────────────────────────────
def arcsinh_stretch(data: np.ndarray, slider: int) -> tuple[np.ndarray, float, float]:
    """Arcsinh stretch.  slider 1 (linear) -> 10 (aggressive).  Returns (disp, 0, 1)."""
    beta  = 10.0 ** (-(slider - 1) * 2.0 / 9.0)
    flat  = data.ravel()
    vlo   = float(np.percentile(flat, 0.5))
    vhi   = float(np.percentile(flat, 99.5))
    norm  = np.clip((data - vlo) / max(vhi - vlo, 1.0), 0.0, 1.0)
    denom = float(np.arcsinh(1.0 / beta))
    stretched = np.arcsinh(norm / beta) / (denom if denom else 1.0)
    return stretched, 0.0, 1.0


def extract_spectrum(data, target_ys, bg_above_ys, bg_below_ys):
    h, w = data.shape
    def clamp(a, b): return max(0, min(a, h)), max(0, min(b, h))
    t0, t1 = clamp(*sorted(target_ys))
    a0, a1 = clamp(*sorted(bg_above_ys))
    b0, b1 = clamp(*sorted(bg_below_ys))
    n_target   = max(1, t1 - t0)
    target_sum = np.sum(data[t0:t1, :], axis=0)
    bg_rows    = []
    if a1 > a0: bg_rows.append(data[a0:a1, :])
    if b1 > b0: bg_rows.append(data[b0:b1, :])
    bg_per_row = (np.mean(np.concatenate(bg_rows, axis=0), axis=0)
                  if bg_rows else np.zeros(w, dtype=np.float32))
    return np.arange(w), target_sum - bg_per_row * n_target, bg_per_row, target_sum, n_target


def compute_snr(spectrum, bg_per_row, n_target, conv_gain, read_noise):
    G = max(conv_gain, 0.001); R = max(read_noise, 0.1)
    sig_e  = np.maximum(spectrum, 0.0) * G
    bg_e   = np.maximum(bg_per_row, 0.0) * G
    return sig_e / np.sqrt(np.maximum(sig_e + n_target * (bg_e + R**2), 1.0))


def sat_runs(data, sat_limit, y0=0, y1=None):
    if y1 is None: y1 = data.shape[0]
    col_sat = np.any(data[max(0,y0):min(data.shape[0],y1), :] > sat_limit, axis=0)
    runs, in_run, start = [], False, 0
    for i, s in enumerate(col_sat):
        if s and not in_run:  start = i; in_run = True
        elif not s and in_run: runs.append((start, i - 1)); in_run = False
    if in_run: runs.append((start, len(col_sat) - 1))
    return runs


# ── Y-axis formatter: show 250k instead of 2.5e5 ──────────────────────────────
def _fmt_spec_y(val, pos):
    av = abs(val)
    if av == 0:
        return "0"
    elif av >= 1e6:
        return f"{val/1e6:.2g}M"
    elif av >= 1e3:
        return f"{val/1e3:.3g}k"
    elif av >= 1:
        return f"{val:.3g}"
    else:
        return f"{val:.2g}"


# ── Flatness filter ───────────────────────────────────────────────────────────
def compute_flatness_mask(spec: np.ndarray, central_fraction: float = 0.35,
                          deriv_window: int = 7, threshold: float = 50.0) -> np.ndarray:
    """
    Bool mask over full spectrum width; True = continuum column.
    Only the central `central_fraction` of columns is ever flagged as continuum;
    the outer margins stay False (excluded) to avoid smile/fishtail distortion.
    """
    n = len(spec)
    margin = int(n * (1.0 - central_fraction) / 2.0)
    c0, c1 = margin, n - margin
    mask = np.zeros(n, dtype=bool)
    if c1 - c0 < max(deriv_window, 4):
        return mask
    sub = spec[c0:c1].astype(np.float64)
    hw = deriv_window // 2
    # Savitzky-Golay first-derivative kernel: least-squares linear slope over the window.
    # Equivalent to the per-element np.polyfit loop but vectorized via convolution.
    kernel = np.arange(-hw, hw + 1, dtype=np.float64)
    norm = float(np.dot(kernel, kernel))
    if norm > 0:
        kernel /= norm
    deriv = np.convolve(sub, kernel[::-1], mode='same')
    mask[c0:c1] = np.abs(deriv) <= threshold
    return mask


def _sat_runs_from_mask(mask: np.ndarray) -> list[tuple[int, int]]:
    """Convert a boolean array to (start, end) run-length pairs where mask is True."""
    runs, in_run, start = [], False, 0
    for i, v in enumerate(mask):
        if v and not in_run:
            start = i; in_run = True
        elif not v and in_run:
            runs.append((start, i - 1)); in_run = False
    if in_run:
        runs.append((start, len(mask) - 1))
    return runs


def _spatial_profile_from_continuum(data: np.ndarray, cont_mask: np.ndarray,
                                    y0: int, y1: int) -> np.ndarray | None:
    """Median-combine spatial profiles (column slices) across continuum columns."""
    cols = np.where(cont_mask)[0]
    if len(cols) < 10:
        return None
    h = data.shape[0]
    y0c, y1c = max(0, y0), min(h, y1)
    if y1c <= y0c:
        return None
    return np.median(data[y0c:y1c, cols], axis=1).astype(np.float64)


def fit_gaussian_spatial(profile: np.ndarray,
                         residual_threshold: float = 0.30
                         ) -> tuple[float | None, float | None, bool]:
    """
    Fit Gaussian + constant to a 1D spatial profile.
    Returns (fwhm_px, centroid_px, reliable).
    Uses astropy.modeling (already in deps) — no scipy required.
    """
    try:
        from astropy.modeling import models, fitting
        if len(profile) < 5:
            return None, None, False
        x = np.arange(len(profile), dtype=float)
        bg  = float(np.percentile(profile, 15))
        amp = float(np.max(profile)) - bg
        if amp <= 0:
            return None, None, False
        cen = float(np.argmax(profile))
        sig = max(len(profile) / 8.0, 2.0)
        g = models.Gaussian1D(amplitude=amp, mean=cen, stddev=sig)
        g += models.Const1D(amplitude=bg)
        g[0].amplitude.bounds = (0, None)
        g[0].stddev.bounds    = (1.0, len(profile) / 2.0)
        fitter = fitting.LevMarLSQFitter()
        gf = fitter(g, x, profile.astype(float), maxiter=300)
        residual = float(np.std(profile - gf(x))) / max(amp, 1.0)
        reliable = (residual < residual_threshold and
                    fitter.fit_info.get("ierr", 5) in (1, 2, 3, 4))
        return 2.355 * abs(gf[0].stddev.value), float(gf[0].mean.value), reliable
    except Exception:
        return None, None, False


# ── Online statistics (Welford) ───────────────────────────────────────────────
class WelfordStats:
    """Per-column running mean/variance using Welford's numerically stable algorithm."""

    def __init__(self, n_cols: int):
        self.n_cols = n_cols
        self.n      = 0
        self.mean   = np.zeros(n_cols, dtype=np.float64)
        self.M2     = np.zeros(n_cols, dtype=np.float64)

    def reset(self):
        self.n = 0; self.mean[:] = 0.0; self.M2[:] = 0.0

    def update(self, x: np.ndarray):
        self.n  += 1
        delta    = x - self.mean
        self.mean += delta / self.n
        self.M2  += delta * (x - self.mean)

    def variance(self) -> np.ndarray:
        return self.M2 / (self.n - 1) if self.n >= 2 else np.zeros(self.n_cols)

    def std(self) -> np.ndarray:
        return np.sqrt(np.maximum(self.variance(), 0.0))

    def stderr(self) -> np.ndarray:
        return self.std() / np.sqrt(max(self.n, 1))


# ── Frame record ──────────────────────────────────────────────────────────────
@dataclass
class FrameRecord:
    frame_number:  int
    filename:      str
    filepath:      str           = ""
    timestamp:     str           = ""
    peak_adu:      float         = 0.0
    sat_limit:     float         = 0.0
    continuum_snr: float | None  = None
    fwhm_px:       float | None  = None
    fwhm_reliable: bool          = True
    n_continuum:   int           = 0
    inclusion:     str           = "included"   # 'included' | 'excluded' | 'flagged'
    flag_reasons:  list          = field(default_factory=list)
    user_kept:     bool          = False        # flagged but user explicitly chose to keep

    @property
    def peak_fill(self) -> float:
        return self.peak_adu / self.sat_limit if self.sat_limit > 0 else 0.0


# ── Session data ──────────────────────────────────────────────────────────────
class SessionData:
    """Accumulates per-frame metrics and session-level online statistics."""

    def __init__(self):
        self.records:     list[FrameRecord]        = []
        self._spectra:    dict[int, np.ndarray]    = {}
        self._cont_masks: dict[int, np.ndarray]    = {}
        self._n_cols:     int                      = 0
        self.welford:     WelfordStats | None      = None
        self.persistence: np.ndarray | None        = None   # fraction per column
        self.snr_history: list[float]              = []     # cont. SNR per included frame

    # ── add a new frame ───────────────────────────────────────────────────────
    def add_frame(self, rec: FrameRecord, spec: np.ndarray | None,
                  cont_mask: np.ndarray | None):
        self.records.append(rec)
        fn = rec.frame_number
        if spec is not None:
            self._spectra[fn]    = spec.astype(np.float64)
        if cont_mask is not None:
            self._cont_masks[fn] = cont_mask.copy()
        if spec is not None:
            n = len(spec)
            if n != self._n_cols:
                self._n_cols     = n
                self.welford     = WelfordStats(n)
                self.persistence = np.zeros(n)
                self.snr_history = []
        if rec.inclusion != "excluded" and spec is not None:
            self._incremental(spec, cont_mask)

    def _incremental(self, spec: np.ndarray, mask: np.ndarray | None):
        wf = self.welford
        if wf is None:
            return
        prev_mean = wf.mean.copy()
        prev_std  = wf.std().copy()
        wf.update(spec)
        if wf.n >= 3 and self.persistence is not None:
            self.persistence += (spec > prev_mean + 2.0 * prev_std).astype(float)
        # Session SNR = quadrature sum of per-frame photon SNR → grows as SNR_1·√N
        snrs = [r.continuum_snr for r in self.records
                if r.inclusion != "excluded" and r.continuum_snr is not None]
        if snrs:
            self.snr_history.append(float(np.sqrt(sum(s * s for s in snrs))))

    # ── full Welford replay after inclusion state change ──────────────────────
    def recompute(self):
        included = [r for r in self.records if r.inclusion != "excluded"]
        if not included or self._n_cols == 0:
            self.welford = None; self.persistence = None; self.snr_history = []; return
        wf      = WelfordStats(self._n_cols)
        persist = np.zeros(self._n_cols, dtype=np.float64)
        snr_h: list[float] = []
        for i, rec in enumerate(included):
            spec = self._spectra.get(rec.frame_number)
            if spec is None or len(spec) != self._n_cols:
                continue
            if wf.n >= 2:
                thresh = wf.mean + 2.0 * wf.std()
                persist += (spec > thresh).astype(np.float64)
            wf.update(spec)
            # Session SNR = quadrature sum of per-frame photon SNR → grows as SNR_1·√N
            snrs = [r.continuum_snr for r in included[:i + 1]
                    if r.continuum_snr is not None]
            if snrs:
                snr_h.append(float(np.sqrt(sum(s * s for s in snrs))))
        self.welford     = wf
        self.persistence = persist / max(len(included), 1)
        self.snr_history = snr_h

    # ── convenience properties ────────────────────────────────────────────────
    @property
    def included(self) -> list[FrameRecord]:
        return [r for r in self.records if r.inclusion != "excluded"]

    @property
    def n_included(self) -> int:
        return sum(1 for r in self.records if r.inclusion != "excluded")

    @property
    def n_flagged(self) -> int:
        return sum(1 for r in self.records if r.inclusion == "flagged")

    @property
    def baseline_fwhm(self) -> float | None:
        vals = [r.fwhm_px for r in self.included
                if r.fwhm_px is not None and r.fwhm_reliable]
        return float(np.median(vals)) if vals else None

    @property
    def std_fwhm(self) -> float | None:
        vals = [r.fwhm_px for r in self.included
                if r.fwhm_px is not None and r.fwhm_reliable]
        return float(np.std(vals)) if len(vals) >= 2 else None

    @property
    def mean_cont_snr(self) -> float | None:
        vals = [r.continuum_snr for r in self.included if r.continuum_snr is not None]
        return float(np.mean(vals)) if vals else None

    @property
    def std_cont_snr(self) -> float | None:
        vals = [r.continuum_snr for r in self.included if r.continuum_snr is not None]
        return float(np.std(vals)) if len(vals) >= 2 else None

    def autoflag_frame(self, rec: FrameRecord, cfg: dict) -> list[str]:
        """Return auto-flag reasons for rec (empty list = no flag)."""
        reasons = []
        if cfg.get("autoflag_continuum_on", True) and rec.n_continuum < 10:
            reasons.append("< 10 continuum cols")
        if cfg.get("autoflag_sat_on", True) and rec.peak_fill >= 1.0:
            reasons.append("saturated")
        mu_snr = self.mean_cont_snr; sd_snr = self.std_cont_snr
        sig_s  = cfg.get("autoflag_snr_sigma", 2.0)
        if (cfg.get("autoflag_snr_on", True) and rec.continuum_snr is not None
                and mu_snr is not None and sd_snr is not None and sd_snr > 0
                and rec.continuum_snr < mu_snr - sig_s * sd_snr):
            reasons.append(f"SNR {rec.continuum_snr:.0f} < mean−{sig_s:.0f}σ")
        bl_fw  = self.baseline_fwhm; sd_fw = self.std_fwhm
        sig_f  = cfg.get("autoflag_fwhm_sigma", 2.0)
        if (cfg.get("autoflag_fwhm_on", True) and rec.fwhm_px is not None
                and rec.fwhm_reliable and bl_fw is not None
                and sd_fw is not None and sd_fw > 0
                and rec.fwhm_px > bl_fw + sig_f * sd_fw):
            reasons.append(f"FWHM {rec.fwhm_px:.1f}px > baseline+{sig_f:.0f}σ")
        return reasons


# ── Line definitions for draggable handles ────────────────────────────────────
# Returns fresh tuples so colors always reflect the active palette after a theme switch.
def _line_defs() -> list:
    return [
        ("bga_top", "BG▲ top",  BG_C,     "--"),
        ("bga_bot", "BG▲ bot",  BG_C,     "--"),
        ("tgt_top", "TGT top",  TARGET_C, "-"),
        ("tgt_bot", "TGT bot",  TARGET_C, "-"),
        ("bgb_top", "BG▼ top",  BG_C,     "--"),
        ("bgb_bot", "BG▼ bot",  BG_C,     "--"),
    ]

_CFG_KEYS = {
    "tgt_top": "target_y_start",   "tgt_bot": "target_y_end",
    "bga_top": "bg_above_y_start", "bga_bot": "bg_above_y_end",
    "bgb_top": "bg_below_y_start", "bgb_bot": "bg_below_y_end",
}


# ── Image canvas ───────────────────────────────────────────────────────────────
class ImageCanvas(FigureCanvas):
    line_released  = pyqtSignal()
    zoom_x_changed = pyqtSignal(float, float)
    zoom_reset_sig = pyqtSignal()

    def __init__(self):
        self.fig = Figure(facecolor=DARK_BG)
        super().__init__(self.fig)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor(DARK_BG)
        self.fig.subplots_adjust(left=0.07, right=0.99, top=0.99, bottom=0.07)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._region: dict[str, int] = {k: 0 for k in _CFG_KEYS}
        self._img_h = 2160; self._img_w = 3840
        self._mpl_lines: dict = {}; self._mpl_hdls: dict = {}; self._mpl_lbls: dict = {}
        self._dragging: str | None = None

        # Zoom state
        self._zoom_mode: bool       = False
        self._zoom_start            = None   # (x, y) data coords on press
        self._zoom_patch            = None   # amber Rectangle being drawn
        self._full_xlim             = None   # saved full view limits
        self._full_ylim             = None

        self.mpl_connect("button_press_event",   self._on_press)
        self.mpl_connect("motion_notify_event",  self._on_motion)
        self.mpl_connect("button_release_event", self._on_release)

    def get_region(self) -> dict:
        return dict(self._region)

    def region_to_cfg(self, cfg: dict):
        for lk, ck in _CFG_KEYS.items():
            cfg[ck] = self._region[lk]

    def refresh(self, fits_data, cfg, stretch_val):
        for lk, ck in _CFG_KEYS.items():
            self._region[lk] = int(cfg[ck])
        self.fig.set_facecolor(DARK_BG)
        self.ax.cla()
        self.ax.set_facecolor(DARK_BG)
        for sp in self.ax.spines.values(): sp.set_edgecolor(DARK_BORDER)
        self.ax.tick_params(colors=TEXT, labelsize=8)
        self.ax.set_xlabel("X pixel", color=TEXT, fontsize=9)
        self.ax.set_ylabel("Y pixel", color=TEXT, fontsize=9)
        self._mpl_lines.clear(); self._mpl_hdls.clear(); self._mpl_lbls.clear()

        # Reset zoom state on image reload
        was_zoomed = self._full_xlim is not None
        self._full_xlim = None
        self._full_ylim = None
        self._zoom_patch = None
        self._zoom_start = None

        if fits_data is None:
            self.ax.text(0.5, 0.5, "No image loaded", color=TEXT,
                         ha="center", va="center", transform=self.ax.transAxes, fontsize=14)
            self.draw_idle()
            if was_zoomed:
                self.zoom_reset_sig.emit()
            return

        data = fits_data["data"]; h, w = data.shape
        self._img_h = h; self._img_w = w
        sat_limit = cfg["saturation_threshold"] * fits_data["full_range"]

        disp, vlo, vhi = arcsinh_stretch(data, stretch_val)
        self.ax.imshow(disp, origin="upper", cmap="gray",
                       vmin=vlo, vmax=vhi, aspect="auto", interpolation="nearest")

        # Saturation bands — no edge lines, stronger alpha, SAT label on first run
        runs = sat_runs(data, sat_limit)
        for i, (cs, ce) in enumerate(runs):
            self.ax.axvspan(cs - 0.5, ce + 0.5, facecolor=SAT_C, alpha=0.30, zorder=4)
            if i == 0:
                # Blended transform: data x-coords, axes y-coords (0=bottom, 1=top)
                mid_x = (cs + ce) / 2.0
                self.ax.text(mid_x, 0.97, "SAT", color=SAT_C, fontsize=7,
                             ha="center", va="top",
                             transform=self.ax.get_xaxis_transform(),
                             zorder=6, alpha=0.95)

        # Region fills
        def shade(y0, y1, col):
            y0c, y1c = max(0, y0), min(h, y1)
            if y1c > y0c:
                self.ax.add_patch(Rectangle((0, y0c), w, y1c - y0c,
                    facecolor=col, alpha=0.07, edgecolor="none", zorder=3))
        shade(cfg["target_y_start"],   cfg["target_y_end"],   TARGET_C)
        shade(cfg["bg_above_y_start"], cfg["bg_above_y_end"], BG_C)
        shade(cfg["bg_below_y_start"], cfg["bg_below_y_end"], BG_C)

        self._draw_lines(w, h)
        self.ax.set_xlim(0, w); self.ax.set_ylim(h, 0)
        self.draw_idle()
        if was_zoomed:
            self.zoom_reset_sig.emit()

    def update_lines_only(self):
        for key, line in self._mpl_lines.items():
            y = self._region[key]
            line.set_ydata([y, y])
        for key, hdl in self._mpl_hdls.items():
            hdl.set_ydata([self._region[key]])
        for key, lbl in self._mpl_lbls.items():
            lbl.set_position((lbl.get_position()[0], self._region[key]))
        self.draw_idle()

    def _draw_lines(self, w, h):
        for key, label, color, ls in _line_defs():
            y = self._region[key]
            line, = self.ax.plot([0, w], [y, y], color=color, lw=1.3,
                                 ls=ls, alpha=0.9, zorder=8)
            hdl,  = self.ax.plot([22], [y], marker=">", color=color,
                                  ms=8, zorder=9, alpha=0.95,
                                  markeredgecolor=DARK_BG, markeredgewidth=0.5)
            lbl   = self.ax.text(38, y, label, color=color, fontsize=7,
                                 va="center", zorder=9,
                                 bbox=dict(facecolor=DARK_BG, alpha=0.55, pad=1,
                                           edgecolor="none"))
            self._mpl_lines[key] = line
            self._mpl_hdls[key]  = hdl
            self._mpl_lbls[key]  = lbl

    def _hit(self, event) -> str | None:
        best_key, best_d = None, 11.0
        for key, line in self._mpl_lines.items():
            yd = float(line.get_ydata()[0])
            ys = self.ax.transData.transform((0, yd))[1]
            d  = abs(event.y - ys)
            if d < best_d: best_d = d; best_key = key
        return best_key

    def set_zoom_mode(self, enabled: bool):
        """Toggle rubber-band zoom mode on/off."""
        self._zoom_mode = enabled
        cursor = Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor
        self.setCursor(QCursor(cursor))

    def reset_zoom(self):
        """Restore full image view and notify spectrum canvas."""
        if self._full_xlim is not None:
            self.ax.set_xlim(self._full_xlim)
            self.ax.set_ylim(self._full_ylim)
            self._full_xlim = None
            self._full_ylim = None
            self.draw_idle()
            self.zoom_reset_sig.emit()

    def _on_press(self, event):
        if event.inaxes != self.ax or event.button != 1:
            return
        if self._zoom_mode:
            if event.xdata is not None and event.ydata is not None:
                self._zoom_start = (event.xdata, event.ydata)
                self._zoom_patch = Rectangle(
                    (event.xdata, event.ydata), 0, 0,
                    linewidth=1.5, edgecolor=ACCENT, facecolor=ACCENT,
                    alpha=0.12, zorder=10, linestyle="--"
                )
                self.ax.add_patch(self._zoom_patch)
                self.draw_idle()
        else:
            self._dragging = self._hit(event)
            if self._dragging:
                self.setCursor(QCursor(Qt.CursorShape.SizeVerCursor))

    def _on_motion(self, event):
        if self._zoom_mode:
            if event.inaxes == self.ax:
                self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
            if (self._zoom_start is not None and self._zoom_patch is not None
                    and event.inaxes == self.ax
                    and event.xdata is not None and event.ydata is not None):
                x0, y0 = self._zoom_start
                x1, y1 = event.xdata, event.ydata
                self._zoom_patch.set_bounds(
                    min(x0, x1), min(y0, y1),
                    abs(x1 - x0), abs(y1 - y0)
                )
                self.draw_idle()
            return

        # Normal drag mode
        if event.inaxes == self.ax:
            self.setCursor(QCursor(Qt.CursorShape.SizeVerCursor
                           if self._hit(event) else Qt.CursorShape.ArrowCursor))
        if not self._dragging or event.inaxes != self.ax or event.ydata is None:
            return
        y = int(round(max(0, min(event.ydata, self._img_h - 1))))
        self._region[self._dragging] = y
        self.update_lines_only()

    def _on_release(self, event):
        if self._zoom_mode and self._zoom_start is not None:
            # Clean up the rubber-band rectangle
            if self._zoom_patch is not None:
                self._zoom_patch.remove()
                self._zoom_patch = None
            x0, y0 = self._zoom_start
            self._zoom_start = None
            if (event.xdata is not None and event.ydata is not None
                    and abs(event.xdata - x0) > 5
                    and abs(event.ydata - y0) > 5):
                # Save full limits before first zoom
                if self._full_xlim is None:
                    self._full_xlim = self.ax.get_xlim()
                    self._full_ylim = self.ax.get_ylim()
                xl = sorted([x0, event.xdata])
                yl = sorted([y0, event.ydata])
                self.ax.set_xlim(xl[0], xl[1])
                # Image y-axis is inverted (origin=upper): larger row number = lower
                self.ax.set_ylim(max(yl), min(yl))
                self.draw_idle()
                self.zoom_x_changed.emit(xl[0], xl[1])
            else:
                self.draw_idle()
            return

        if self._dragging:
            self._dragging = None
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
            self.line_released.emit()


# ── Spectrum canvas ────────────────────────────────────────────────────────────
class SpectrumCanvas(FigureCanvas):
    def __init__(self):
        self.fig = Figure(facecolor=DARK_BG)
        super().__init__(self.fig)
        self.ax     = self.fig.add_subplot(111)
        self.ax_snr = self.ax.twinx()
        self.ax.set_facecolor(DARK_BG)
        self.fig.subplots_adjust(left=0.09, right=0.86, top=0.97, bottom=0.11)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._full_xlim = None

    def refresh(self, fits_data, cfg, show_snr, normalize):
        self.fig.set_facecolor(DARK_BG)
        self.ax.cla(); self.ax_snr.cla()
        self._full_xlim = None
        for ax in (self.ax, self.ax_snr):
            ax.set_facecolor(DARK_BG)
            ax.tick_params(colors=TEXT, labelsize=8)
            for sp in ax.spines.values(): sp.set_edgecolor(DARK_BORDER)
        if fits_data is None:
            self.ax.text(0.5, 0.5, "No data", color=TEXT, ha="center", va="center",
                         transform=self.ax.transAxes); self.draw_idle(); return None

        data       = fits_data["data"]
        full_range = fits_data["full_range"]
        sat_limit  = cfg["saturation_threshold"] * full_range

        x, spec, bg, tsum, n = extract_spectrum(
            data,
            (cfg["target_y_start"],   cfg["target_y_end"]),
            (cfg["bg_above_y_start"], cfg["bg_above_y_end"]),
            (cfg["bg_below_y_start"], cfg["bg_below_y_end"]),
        )

        sat_line = sat_limit * n
        sp_plot  = spec.copy()
        raw_plot = tsum.copy()
        if normalize:
            pk = float(np.max(np.abs(sp_plot))) or 1.0
            sp_plot /= pk; raw_plot /= pk; sat_line /= pk

        self.ax.plot(x, raw_plot,  color=RAW_C,  lw=0.5, label="Raw sum",         zorder=2)
        self.ax.plot(x, sp_plot,   color=SPEC_C, lw=1.1, label="Extracted bg-sub", zorder=3)
        self.ax.axhline(sat_line,  color=SAT_C,  lw=1.0, ls="--", alpha=0.85,
                        label=f"Sat. limit ({int(cfg['saturation_threshold']*100)}%)", zorder=4)

        # Saturation column shading
        for cs, ce in sat_runs(data, sat_limit,
                               y0=cfg["target_y_start"], y1=cfg["target_y_end"]):
            self.ax.axvspan(cs - 0.5, ce + 0.5, facecolor=SAT_C, alpha=0.18, zorder=3)

        # Y autoscale to extracted spectrum
        smin = float(np.min(sp_plot)); smax = float(np.max(sp_plot))
        pad  = max((smax - smin) * 0.06, 1.0)
        ytop = max(smax + pad, sat_line if sat_line < smax * 3 else smax + pad)
        self.ax.set_ylim(smin - pad, ytop + pad)

        ylabel = "Intensity (norm.)" if normalize else "Intensity (ADU · rows)"
        self.ax.set_xlabel("X pixel  (∝ wavelength)", color=TEXT, fontsize=9)
        self.ax.set_ylabel(ylabel, color=TEXT, fontsize=9)

        # k/M formatter for y-axis (not when normalized — values are 0–1)
        if not normalize:
            self.ax.yaxis.set_major_formatter(FuncFormatter(_fmt_spec_y))

        if show_snr:
            snr = compute_snr(spec, bg, n, cfg["conversion_gain"], cfg["read_noise"])
            self.ax_snr.plot(x, snr, color=SNR_C, lw=0.9, ls=":",
                             alpha=0.9, label="SNR  (right axis)", zorder=2)
            self.ax_snr.set_ylabel("SNR", color=TEXT, fontsize=9)
            self.ax_snr.yaxis.set_label_position("right")
            self.ax_snr.yaxis.label.set_color(TEXT)
            self.ax_snr.tick_params(axis="y", colors=TEXT, labelsize=8)
            self.ax_snr.spines["right"].set_edgecolor(DARK_BORDER)
        else:
            self.ax_snr.set_yticks([])
            self.ax_snr.spines["right"].set_edgecolor(DARK_BORDER)

        h1, l1 = self.ax.get_legend_handles_labels()
        h2, l2 = self.ax_snr.get_legend_handles_labels()
        self.ax.legend(h1 + h2, l1 + l2, loc="upper right", fontsize=8,
                       facecolor=DARK_PANEL, edgecolor=DARK_BORDER, labelcolor=TEXT)

        # Save full xlim for reset_xrange()
        self._full_xlim = self.ax.get_xlim()
        self.draw_idle()
        return x, spec, bg, n

    def set_xrange(self, x_min: float, x_max: float, spec_data=None):
        """Synchronise x-axis with image canvas zoom."""
        self.ax.set_xlim(x_min, x_max)
        self.draw_idle()

    def reset_xrange(self):
        """Restore full x-axis view saved during last refresh()."""
        if self._full_xlim is not None:
            self.ax.set_xlim(self._full_xlim)
            self._full_xlim = None
            self.draw_idle()


# ── Advisory panel ─────────────────────────────────────────────────────────────
class AdvisoryPanel(QWidget):
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        # ── Exposure Advisory ──
        exp_grp, exp_lay = section_box("Exposure Advisory", "advisory")
        g = QGridLayout()
        g.setVerticalSpacing(2)
        g.setHorizontalSpacing(6)
        g.setColumnStretch(1, 1)
        g.setColumnStretch(3, 1)
        exp_lay.addLayout(g)
        outer.addWidget(exp_grp)

        # ── Gain Advisory ──
        gain_grp, gain_lay = section_box("Gain Advisory  (ASI585MM Pro)", "gain")
        g2 = QGridLayout()
        g2.setVerticalSpacing(2)
        g2.setHorizontalSpacing(6)
        g2.setColumnStretch(1, 1)
        g2.setColumnStretch(3, 1)
        gain_lay.addLayout(g2)
        outer.addWidget(gain_grp)
        self._gain_grp = gain_grp

        self._rows: dict[str, QLabel] = {}
        self._key_labels: list[QLabel] = []

        # Exposure advisory rows (2 items per row except Exp. suggestion)
        self._add_pair(g, 0, "Exposure",         "Gain (slider)")
        self._add_pair(g, 1, "Peak fill",         "Peak SNR")
        self._add_pair(g, 2, "Frames: SNR 100",   "Noise regime")
        self._add_solo(g, 3, "Exp. suggestion")

        # Gain advisory rows
        self._add_pair(g2, 0, "Gain regime",      "Full well")
        self._add_solo(g2, 1, "Gain suggestion")

    def _mk_key(self, name: str) -> QLabel:
        kl = QLabel(name + ":")
        kl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        kl.setStyleSheet(f"color:{TEXT_DIM}; font-size:{F_SM}; border:none;")
        self._key_labels.append(kl)
        return kl

    def _mk_val(self, name: str) -> QLabel:
        vl = QLabel("—")
        vl.setStyleSheet(
            f"color:{ACCENT}; font-size:{F_BASE}; font-weight:bold; border:none;")
        self._rows[name] = vl
        return vl

    def _add_pair(self, grid, row: int, name1: str, name2: str):
        grid.addWidget(self._mk_key(name1), row, 0)
        grid.addWidget(self._mk_val(name1), row, 1)
        grid.addWidget(self._mk_key(name2), row, 2)
        grid.addWidget(self._mk_val(name2), row, 3)

    def _add_solo(self, grid, row: int, name: str):
        grid.addWidget(self._mk_key(name), row, 0)
        vl = self._mk_val(name)
        grid.addWidget(vl, row, 1, 1, 3)

    def _add_row(self, grid, row, name):
        grid.addWidget(self._mk_key(name), row, 0)
        grid.addWidget(self._mk_val(name), row, 1)

    def _set(self, name, text, color=ACCENT):
        if name in self._rows:
            self._rows[name].setText(text)
            self._rows[name].setStyleSheet(
                f"color:{color}; font-size:{F_BASE}; font-weight:bold; border:none;")

    def show_gain_section(self, visible: bool):
        self._gain_grp.setVisible(visible)

    def _restyle(self):
        if _is_day_mode:
            for kl in self._key_labels:
                kl.setStyleSheet("")
            for vl in self._rows.values():
                vl.setStyleSheet("")
            return
        for kl in self._key_labels:
            kl.setStyleSheet(f"color:{TEXT_DIM}; font-size:{F_SM}; border:none;")
        for vl in self._rows.values():
            vl.setStyleSheet(
                f"color:{ACCENT}; font-size:{F_BASE}; font-weight:bold; border:none;")

    def refresh_data(self, fits_data, cfg, spectrum, bg_per_row, n_target, gain_on=False):
        self.show_gain_section(gain_on)
        if fits_data is None or spectrum is None:
            for r in self._rows: self._set(r, "—")
            return

        data       = fits_data["data"]
        full_range = fits_data["full_range"]
        sat_limit  = cfg["saturation_threshold"] * full_range

        # ── Exposure + Gain slider ──
        et = fits_data.get("exptime")
        self._set("Exposure", f"{float(et):.1f} s" if et is not None else "—")
        gs = fits_data.get("gain_slider")
        self._set("Gain (slider)",
                  f"{gs}  (ZWO slider)" if gs is not None else "—", color=TEXT_DIM)

        # ── Peak fill ──
        h   = data.shape[0]
        y0  = max(0, cfg["target_y_start"]); y1 = min(h, cfg["target_y_end"])
        peak = float(np.max(data[y0:y1, :])) if y1 > y0 else 0.0
        fill = peak / sat_limit if sat_limit > 0 else 0.0
        fp   = fill * 100.0

        # First saturated column in target region
        runs_tgt = sat_runs(data, sat_limit, y0=y0, y1=y1)
        sat_col_str = f"  (first sat. col {runs_tgt[0][0]})" if runs_tgt else ""

        if   fp >= 100: fc, ft = WARN,    f"{fp:.0f}%  ⚠ SATURATED{sat_col_str}"
        elif fp >=  90: fc, ft = WARN,    f"{fp:.0f}%  ⚠ Near saturation{sat_col_str}"
        elif fp >=  65: fc, ft = OK_COL,  f"{fp:.0f}%  ✓ Good"
        else:           fc, ft = TEXT_DIM, f"{fp:.0f}%  ↑ Underexposed"
        self._set("Peak fill", ft, color=fc)

        # ── Peak SNR ──
        G   = cfg["conversion_gain"]; R = cfg["read_noise"]
        snr = compute_snr(spectrum, bg_per_row, n_target, G, R)
        pk_snr = float(np.max(snr)); pk_col = int(np.argmax(snr))
        self._set("Peak SNR", f"{pk_snr:.0f}  at col {pk_col}")

        # ── Frames needed to reach SNR 100 ──
        if pk_snr >= 100:
            self._set("Frames: SNR 100", "✓ Already SNR ≥ 100", color=OK_COL)
        elif pk_snr > 0.1:
            n_frames = math.ceil((100.0 / pk_snr) ** 2)
            if et is not None:
                total_t = n_frames * float(et)
                self._set("Frames: SNR 100",
                          f"{n_frames} frames  ({total_t:.0f} s total)", color=ACCENT)
            else:
                self._set("Frames: SNR 100", f"{n_frames} frames", color=ACCENT)
        else:
            self._set("Frames: SNR 100", "— (SNR too low)", color=TEXT_DIM)

        # ── Noise regime ──
        sig_e = float(np.mean(np.maximum(spectrum, 0.0))) * G
        bg_e  = float(np.mean(np.maximum(bg_per_row, 0.0))) * G * n_target
        rn2   = n_target * R ** 2
        if   bg_e > 3 * sig_e and bg_e > rn2: regime = "bg-limited  (∝ √t)"
        elif rn2  > bg_e:                       regime = "RN-limited  (∝ t)"
        else:                                   regime = "signal-ltd  (∝ √t)"
        self._set("Noise regime", regime, color=TEXT)

        # ── Exposure suggestion ──
        if et is not None and fill > 0.01:
            t     = float(et)
            t_new = t * (cfg["target_fill"] / fill)
            dsnr  = np.sqrt(abs(t_new / t))
            ns    = pk_snr * dsnr
            if fp >= 100:
                self._set("Exp. suggestion",
                          f"↓ Reduce to {t_new:.1f} s  ->  SNR ~{ns:.0f}  "
                          f"(−{(1-dsnr)*100:.0f}%)", color=WARN)
            elif fill > cfg["target_fill"] * 0.95:
                self._set("Exp. suggestion",
                          f"✓ Near optimal  ({fp:.0f}% of sat. limit)", color=OK_COL)
            else:
                self._set("Exp. suggestion",
                          f"↑ Try {t_new:.1f} s  ->  SNR ~{ns:.0f}  "
                          f"(+{(dsnr-1)*100:.0f}%)", color=ACCENT)
        else:
            self._set("Exp. suggestion", "— (no EXPTIME in header)")

        # ── Gain advisory ──
        if not gain_on:
            return
        if gs is None:
            self._set("Gain regime",      "— (no GAIN in header)", color=TEXT_DIM)
            self._set("Full well",        "—")
            self._set("Gain suggestion",  "—")
            return

        g_val = float(gs)
        e_adu, rn_cam, fw_e = interp_gain(g_val)
        in_hcg = g_val >= HCG_THRESHOLD

        bg_e_px = float(np.mean(np.maximum(bg_per_row, 0.0))) * e_adu
        if   bg_e_px > rn_cam ** 2: g_regime = "background-limited"
        elif rn_cam ** 2 > bg_e_px: g_regime = "read-noise limited"
        else:                        g_regime = "signal-limited"

        hcg_str = "  [HCG mode ✓]" if in_hcg else "  [normal mode]"
        self._set("Gain regime",
                  f"{g_regime}{hcg_str}  RN~{rn_cam:.1f} e-", color=TEXT)

        # Fix dimensional bug: sat_limit is in ADU; convert to electrons for comparison
        sat_limit_e = sat_limit * e_adu
        fw_pct = (fw_e / sat_limit_e * 100.0) if sat_limit_e > 0 else 0.0
        self._set("Full well",
                  f"~{fw_e:,.0f} e-  ({fw_pct:.0f}% of sat. headroom)",
                  color=TEXT)

        if fp >= 90:
            t_val = float(et) if et is not None else None
            if t_val:
                t_new2 = t_val * (cfg["target_fill"] / fill)
                sug = f"↓ Reduce exposure to {t_new2:.1f} s  (keeps gain {int(g_val)}"
                if in_hcg:
                    sug += ", keeps HCG low read noise)"
                    g_low = 100
                    _, rn_low, fw_low = interp_gain(g_low)
                    sug += (f"<br>Alternative: gain {g_low} -> FW ~{fw_low:,.0f} e-, "
                            f"RN ~{rn_low:.1f} e- (loses HCG)")
                else:
                    sug += ", already at high dynamic range)"
            else:
                sug = f"↓ Reduce exposure  (peak at {fp:.0f}%)"
            self._set("Gain suggestion", sug, color=WARN)

        elif g_regime == "read-noise limited" and not in_hcg:
            _, rn_hcg, fw_hcg = interp_gain(HCG_THRESHOLD)
            self._set("Gain suggestion",
                      f"Try gain {HCG_THRESHOLD} (HCG): RN ~{rn_hcg:.1f} e- "
                      f"(4x lower), FW ~{fw_hcg:,.0f} e-",
                      color=ACCENT)

        elif g_regime == "read-noise limited" and in_hcg:
            g_next = min(int(g_val) + 50, 450)
            _, rn_next, fw_next = interp_gain(g_next)
            self._set("Gain suggestion",
                      f"Consider gain {g_next}: RN ~{rn_next:.1f} e-, "
                      f"FW ~{fw_next:,.0f} e-",
                      color=TEXT_DIM)

        elif g_regime == "background-limited":
            if in_hcg:
                if g_val > HCG_THRESHOLD + 10:
                    _, rn_200, fw_200 = interp_gain(HCG_THRESHOLD)
                    self._set("Gain suggestion",
                              f"Background-limited — gain fine. "
                              f"Gain {HCG_THRESHOLD} gives FW ~{fw_200:,.0f} e- "
                              f"at same RN ({rn_200:.1f} e-)",
                              color=OK_COL)
                else:
                    self._set("Gain suggestion",
                              f"Optimal — gain {int(g_val)} in HCG, background-limited",
                              color=OK_COL)
            else:
                _, rn_hcg2, fw_hcg2 = interp_gain(HCG_THRESHOLD)
                self._set("Gain suggestion",
                          f"Gain {int(g_val)} OK. HCG (gain {HCG_THRESHOLD}): "
                          f"4x lower RN ({rn_hcg2:.1f} e-) but FW ~{fw_hcg2:,.0f} e-",
                          color=TEXT)
        else:
            self._set("Gain suggestion", "Gain appears optimal", color=OK_COL)


# ── Region spin-box row ────────────────────────────────────────────────────────
class RegionControl(QWidget):
    changed = pyqtSignal()

    def __init__(self, label, color):
        super().__init__()
        self._color = color
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self._dot = QLabel("█")
        self._dot.setStyleSheet(f"color:{color}; font-size:11pt; border:none;")
        self._dot.setFixedWidth(16)
        self._band_lbl = QLabel(label)
        self._band_lbl.setFixedWidth(62)
        self._band_lbl.setStyleSheet(f"color:{color}; font-size:10pt; font-weight:bold; border:none;")
        self.y0 = QSpinBox(); self.y0.setRange(0, 99999); self.y0.setFixedWidth(65)
        self.y1 = QSpinBox(); self.y1.setRange(0, 99999); self.y1.setFixedWidth(65)
        self.y0.valueChanged.connect(self.changed.emit)
        self.y1.valueChanged.connect(self.changed.emit)
        self._arr = QLabel("->")
        self._arr.setStyleSheet(f"font-size:10pt; color:{TEXT_DIM}; border:none;")
        for w in (self._dot, self._band_lbl, QLabel("Y:"), self.y0, self._arr, self.y1):
            lay.addWidget(w)
        lay.addStretch()

    def _restyle(self):
        if _is_day_mode:
            self._dot.setStyleSheet("")
            self._band_lbl.setStyleSheet("")
            self._arr.setStyleSheet("")
        else:
            self._dot.setStyleSheet(f"color:{self._color}; font-size:11pt; border:none;")
            self._band_lbl.setStyleSheet(f"color:{self._color}; font-size:10pt; font-weight:bold; border:none;")
            self._arr.setStyleSheet(f"font-size:10pt; color:{TEXT_DIM}; border:none;")

    def set_values(self, s, e):
        for sp, v in ((self.y0, s), (self.y1, e)):
            sp.blockSignals(True); sp.setValue(int(v)); sp.blockSignals(False)

    def get_values(self):
        return self.y0.value(), self.y1.value()


# ── FWHM trend canvas ────────────────────────────────────────────────────────
class FWHMCanvas(FigureCanvas):
    def __init__(self):
        self.fig = Figure(facecolor=DARK_BG)
        super().__init__(self.fig)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor(DARK_BG)
        self.fig.subplots_adjust(left=0.14, right=0.97, top=0.92, bottom=0.22)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def refresh(self, session: SessionData, warn_pct: float, alarm_pct: float):
        self.fig.set_facecolor(DARK_BG)
        self.ax.cla()
        self.ax.set_facecolor(DARK_BG)
        for sp in self.ax.spines.values(): sp.set_edgecolor(DARK_BORDER)
        self.ax.tick_params(colors=TEXT, labelsize=8)
        self.ax.set_xlabel("Included frame #", color=TEXT, fontsize=9)
        self.ax.set_ylabel("FWHM (px)", color=TEXT, fontsize=9)
        self.ax.set_title("Spatial FWHM", color=TEXT_HI, fontsize=9, pad=3)

        bl = session.baseline_fwhm
        xs, ys, cs = [], [], []
        for i, rec in enumerate(session.included, 1):
            if rec.fwhm_px is None:
                continue
            xs.append(i)
            ys.append(rec.fwhm_px)
            if not rec.fwhm_reliable:
                cs.append(TEXT_DIM)
            elif bl is not None and rec.fwhm_px > bl * (1 + alarm_pct / 100):
                cs.append(WARN)
            elif bl is not None and rec.fwhm_px > bl * (1 + warn_pct / 100):
                cs.append(ACCENT)
            else:
                cs.append(OK_COL)

        if xs:
            self.ax.plot(xs, ys, color=TEXT_DIM, lw=0.8, zorder=2)
            for x, y, c in zip(xs, ys, cs):
                self.ax.scatter([x], [y], color=c, s=22, zorder=3)
            if bl is not None:
                self.ax.axhline(bl, color=OK_COL, lw=0.8, ls="--", alpha=0.7,
                                label=f"baseline {bl:.1f}px")
                self.ax.axhline(bl * (1 + warn_pct / 100),
                                color=ACCENT, lw=0.6, ls=":", alpha=0.6)
                self.ax.axhline(bl * (1 + alarm_pct / 100),
                                color=WARN,  lw=0.6, ls=":", alpha=0.6)
                self.ax.legend(loc="upper left", fontsize=7,
                               facecolor=DARK_PANEL, edgecolor=DARK_BORDER, labelcolor=TEXT)
        else:
            self.ax.text(0.5, 0.5, "No FWHM data yet", color=TEXT_DIM,
                         ha="center", va="center", transform=self.ax.transAxes, fontsize=10)
        self.draw_idle()


# ── Convergence profile canvas ────────────────────────────────────────────────
class ConvergenceProfileCanvas(FigureCanvas):
    def __init__(self):
        self.fig = Figure(facecolor=DARK_BG)
        super().__init__(self.fig)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor(DARK_BG)
        self.fig.subplots_adjust(left=0.12, right=0.97, top=0.94, bottom=0.13)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(180)
        self._xlim: tuple | None = None   # None = full range
        self._full_xlim: tuple | None = None

    def set_xrange(self, x_min: float, x_max: float):
        self._xlim = (x_min, x_max)
        self.ax.set_xlim(x_min, x_max)
        self.draw_idle()

    def reset_xrange(self):
        self._xlim = None
        if self._full_xlim is not None:
            self.ax.set_xlim(self._full_xlim)
            self.draw_idle()

    def refresh(self, session: SessionData, cont_mask, envelope_sigma: float,
                persistence_threshold: float):
        self.fig.set_facecolor(DARK_BG)
        self.ax.cla()
        self.ax.set_facecolor(DARK_BG)
        for sp in self.ax.spines.values(): sp.set_edgecolor(DARK_BORDER)
        self.ax.tick_params(colors=TEXT, labelsize=7)
        self.ax.set_title("Signal Convergence", color=TEXT_HI, fontsize=9, pad=2)
        self.ax.set_xlabel("X pixel  (∝ wavelength)", color=TEXT, fontsize=8)
        self.ax.set_ylabel("Mean  (ADU·rows)", color=TEXT, fontsize=8)
        self.ax.yaxis.set_major_formatter(FuncFormatter(_fmt_spec_y))
        wf = session.welford
        if wf is not None and wf.n >= 3:
            x   = np.arange(wf.n_cols)
            mu  = wf.mean
            sig = wf.stderr() * envelope_sigma
            self.ax.plot(x, mu, color=SPEC_C, lw=1.0, zorder=3,
                         label=f"mean (N={wf.n})")
            self.ax.fill_between(x, mu - sig, mu + sig,
                                  color=SPEC_C, alpha=0.13, zorder=2,
                                  label=f"±{envelope_sigma:.0f}σ/√N envelope")
            if cont_mask is not None:
                for cs, ce in _sat_runs_from_mask(~cont_mask):
                    self.ax.axvspan(cs - 0.5, ce + 0.5,
                                     facecolor=TEXT_DIM, alpha=0.08, zorder=1)
            if session.persistence is not None:
                pts = np.where(session.persistence >= persistence_threshold)[0]
                if pts.size:
                    ymin = float(np.min(mu - sig))
                    self.ax.scatter(pts, np.full(pts.size, ymin),
                                     color=ACCENT, marker="|", s=40, zorder=4,
                                     label=f"persist ≥{persistence_threshold:.0%}")
            self.ax.legend(loc="upper right", fontsize=7,
                            facecolor=DARK_PANEL, edgecolor=DARK_BORDER, labelcolor=TEXT)
            self._full_xlim = (0, wf.n_cols)
            self.ax.set_xlim(self._xlim if self._xlim else self._full_xlim)
        elif wf is not None and 0 < wf.n < 3:
            self.ax.text(0.5, 0.5, f"Accumulating baseline…  ({wf.n}/3 frames)",
                          color=TEXT_DIM, ha="center", va="center",
                          transform=self.ax.transAxes, fontsize=9)
        else:
            self.ax.text(0.5, 0.5, "No data yet", color=TEXT_DIM,
                          ha="center", va="center",
                          transform=self.ax.transAxes, fontsize=9)
        self.draw_idle()


# ── SNR sparkline canvas ──────────────────────────────────────────────────────
class SNRSparklineCanvas(FigureCanvas):
    def __init__(self):
        self.fig = Figure(facecolor=DARK_BG)
        super().__init__(self.fig)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor(DARK_BG)
        self.fig.subplots_adjust(left=0.12, right=0.97, top=0.90, bottom=0.22)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(120)

    def refresh(self, session: SessionData, snr_target: float):
        self.fig.set_facecolor(DARK_BG)
        self.ax.cla()
        self.ax.set_facecolor(DARK_BG)
        for sp in self.ax.spines.values(): sp.set_edgecolor(DARK_BORDER)
        self.ax.tick_params(colors=TEXT, labelsize=7)
        self.ax.set_xlabel("Included frame #", color=TEXT, fontsize=7)
        self.ax.set_ylabel("Cont. SNR", color=TEXT, fontsize=7)
        title_snr = "Continuum SNR vs. Frame"
        snr_h = session.snr_history
        if len(snr_h) >= 2:
            xs = np.arange(1, len(snr_h) + 1)
            self.ax.plot(xs, snr_h, color=SNR_C, lw=1.0, zorder=3, label="Cont. SNR")
            if snr_h[0] > 0:
                ref = snr_h[0] * np.sqrt(xs)
                self.ax.plot(xs, ref, color=TEXT_DIM, lw=0.6,
                              ls="--", alpha=0.55, label="√N ref")
            if snr_target > 0:
                self.ax.axhline(snr_target, color=ACCENT, lw=0.8, ls="--", alpha=0.8,
                                 label=f"target {snr_target:.0f}")
            if len(snr_h) >= 3 and snr_h[0] > 0:
                ref_vals = snr_h[0] * np.sqrt(np.arange(1, len(snr_h) + 1))
                ratio = np.array(snr_h) / np.maximum(ref_vals, 0.001)
                consec = 0
                for r in ratio:
                    consec = consec + 1 if (r < 0.7 or r > 1.5) else 0
                    if consec >= 3:
                        title_snr = "Cont. SNR  ⚠ transparency/guiding event?"
                        break
            self.ax.legend(loc="upper left", fontsize=7,
                            facecolor=DARK_PANEL, edgecolor=DARK_BORDER, labelcolor=TEXT)
        else:
            self.ax.text(0.5, 0.5, "Need ≥ 2 included frames",
                          color=TEXT_DIM, ha="center", va="center",
                          transform=self.ax.transAxes, fontsize=8)
        title_col = WARN if "⚠" in title_snr else TEXT_HI
        self.ax.set_title(title_snr, color=title_col, fontsize=8, pad=2)
        self.draw_idle()


# ── FWHM panel ────────────────────────────────────────────────────────────────
class FWHMPanel(QWidget):
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)

        # ── collapsible header ────────────────────────────────────────────────
        self._expanded = False
        self._hdr = QPushButton("▶ Spatial FWHM Monitor  —  FWHM: —")
        self._hdr.setCheckable(True)
        self._hdr.setStyleSheet(f"""
            QPushButton {{
                text-align:left; padding:4px 8px;
                background:{DARK_PANEL}; color:{TEXT};
                border:1px solid {DARK_BORDER}; border-radius:3px;
                font-size:11pt;
            }}
            QPushButton:checked {{ color:{ACCENT}; }}
        """)
        self._hdr.toggled.connect(self._toggle)
        hdr_row = QWidget()
        hl = QHBoxLayout(hdr_row)
        hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(0)
        hl.addWidget(self._hdr, stretch=1)
        self._help_btn = HelpButton(HELP["fwhm"])
        hl.addWidget(self._help_btn)
        outer.addWidget(hdr_row)

        # ── body (visible when expanded) ──────────────────────────────────────
        self._body = QWidget()
        bl = QVBoxLayout(self._body)
        bl.setContentsMargins(4, 2, 4, 2)
        bl.setSpacing(3)

        kpi_row = QWidget()
        kl = QHBoxLayout(kpi_row)
        kl.setContentsMargins(0, 0, 0, 0); kl.setSpacing(12)
        self._lbl_fwhm = QLabel("FWHM: —")
        self._lbl_fwhm.setStyleSheet(
            f"color:{ACCENT}; font-size:{F_VAL}; font-weight:bold; border:none;")
        self._lbl_baseline = QLabel("baseline: —")
        self._lbl_baseline.setStyleSheet(
            f"color:{TEXT_DIM}; font-size:11pt; border:none;")
        kl.addWidget(self._lbl_fwhm); kl.addWidget(self._lbl_baseline); kl.addStretch()
        bl.addWidget(kpi_row)

        self._canvas = FWHMCanvas()
        bl.addWidget(self._canvas)

        cfg_row = QWidget()
        cl = QHBoxLayout(cfg_row)
        cl.setContentsMargins(0, 0, 0, 0); cl.setSpacing(8)
        cl.addWidget(QLabel("Warn%:"))
        self.spin_warn = QSpinBox()
        self.spin_warn.setRange(5, 100); self.spin_warn.setValue(20)
        self.spin_warn.setFixedWidth(58)
        cl.addWidget(self.spin_warn)
        cl.addWidget(QLabel("  Alarm%:"))
        self.spin_alarm = QSpinBox()
        self.spin_alarm.setRange(10, 200); self.spin_alarm.setValue(50)
        self.spin_alarm.setFixedWidth(58)
        cl.addWidget(self.spin_alarm)
        cl.addStretch()
        bl.addWidget(cfg_row)

        flat_row = QWidget()
        fl = QHBoxLayout(flat_row)
        fl.setContentsMargins(0, 0, 0, 0); fl.setSpacing(8)
        self._flat_lbl = QLabel("Flatness threshold:")
        self._flat_lbl.setStyleSheet(f"color:{TEXT_DIM}; font-size:10pt; border:none;")
        fl.addWidget(self._flat_lbl)
        self.spin_flat = QDoubleSpinBox()
        self.spin_flat.setRange(1.0, 50000.0)
        self.spin_flat.setSingleStep(10.0)
        self.spin_flat.setValue(500.0)
        self.spin_flat.setFixedWidth(95)
        self.spin_flat.setToolTip(
            "Derivative threshold for continuum column detection.\n"
            "Lower = more sensitive to spectral lines.\n"
            "Shared by all session features.")
        fl.addWidget(self.spin_flat)
        fl.addWidget(QLabel("ADU/col"))
        fl.addStretch()
        bl.addWidget(flat_row)

        self._body.setVisible(False)
        outer.addWidget(self._body)

        self._fwhm_summary = "FWHM: —"

    def _toggle(self, checked: bool):
        self._expanded = checked
        self._update_header()
        self._body.setVisible(checked)

    def _update_header(self):
        arrow = "▼" if self._expanded else "▶"
        self._hdr.setText(f"{arrow} Spatial FWHM Monitor  —  {self._fwhm_summary}")

    def _restyle(self):
        if _is_day_mode:
            self._hdr.setStyleSheet("")
            self._help_btn.setStyleSheet("")
            self._lbl_fwhm.setStyleSheet("")
            self._lbl_baseline.setStyleSheet("")
            self._flat_lbl.setStyleSheet("")
            return
        self._hdr.setStyleSheet(f"""
            QPushButton {{
                text-align:left; padding:4px 8px;
                background:{DARK_PANEL}; color:{TEXT};
                border:1px solid {DARK_BORDER}; border-radius:3px; font-size:11pt;
            }}
            QPushButton:checked {{ color:{ACCENT}; }}
        """)
        self._help_btn.setStyleSheet(f"color:{TEXT_HI}; font-size:12pt; border:none;")
        self._lbl_fwhm.setStyleSheet(
            f"color:{ACCENT}; font-size:{F_VAL}; font-weight:bold; border:none;")
        self._lbl_baseline.setStyleSheet(
            f"color:{TEXT_DIM}; font-size:11pt; border:none;")
        self._flat_lbl.setStyleSheet(f"color:{TEXT_DIM}; font-size:10pt; border:none;")

    def refresh(self, session: SessionData):
        warn  = float(self.spin_warn.value())
        alarm = float(self.spin_alarm.value())
        self._canvas.refresh(session, warn, alarm)
        bl  = session.baseline_fwhm
        inc = session.included
        cur = next((r.fwhm_px for r in reversed(inc) if r.fwhm_px is not None), None)
        if cur is None:
            col = TEXT_DIM
            fwhm_txt = "FWHM: —"
        else:
            if bl and cur > bl * (1 + alarm / 100):
                col = WARN
            elif bl and cur > bl * (1 + warn / 100):
                col = ACCENT
            else:
                col = OK_COL
            fwhm_txt = (f"FWHM: {cur:.1f} px"
                        + ("" if inc and inc[-1].fwhm_reliable else "  (fit unreliable)"))
        self._fwhm_summary = fwhm_txt + (f"  baseline: {bl:.1f} px" if bl else "")
        self._lbl_fwhm.setText(fwhm_txt)
        self._lbl_fwhm.setStyleSheet(
            f"color:{col}; font-size:{F_VAL}; font-weight:bold; border:none;")
        self._lbl_baseline.setText(f"baseline: {bl:.1f} px" if bl else "baseline: —")
        self._update_header()


# ── Convergence panel ─────────────────────────────────────────────────────────
class ConvergencePanel(QWidget):
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)

        self._expanded = False
        self._hdr = QPushButton("▶ Signal Convergence  —  N=0")
        self._hdr.setCheckable(True)
        self._hdr.setStyleSheet(f"""
            QPushButton {{
                text-align:left; padding:4px 8px;
                background:{DARK_PANEL}; color:{TEXT};
                border:1px solid {DARK_BORDER}; border-radius:3px;
                font-size:11pt;
            }}
            QPushButton:checked {{ color:{ACCENT}; }}
        """)
        self._hdr.toggled.connect(self._toggle)
        hdr_row = QWidget()
        hl = QHBoxLayout(hdr_row)
        hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(0)
        hl.addWidget(self._hdr, stretch=1)
        self._help_btn = HelpButton(HELP["convergence"])
        hl.addWidget(self._help_btn)
        outer.addWidget(hdr_row)

        self._body = QWidget()
        bl = QVBoxLayout(self._body)
        bl.setContentsMargins(4, 2, 4, 2)
        bl.setSpacing(3)

        self._canvas = ConvergenceProfileCanvas()
        bl.addWidget(self._canvas)

        cfg_row = QWidget()
        cl = QHBoxLayout(cfg_row)
        cl.setContentsMargins(0, 0, 0, 0); cl.setSpacing(8)
        cl.addWidget(QLabel("Envelope ±"))
        self.spin_sigma = QSpinBox()
        self.spin_sigma.setRange(1, 3); self.spin_sigma.setValue(2)
        self.spin_sigma.setFixedWidth(48)
        cl.addWidget(self.spin_sigma)
        cl.addWidget(QLabel("σ   Persist:"))
        self.spin_persist = QDoubleSpinBox()
        self.spin_persist.setRange(0.50, 1.00); self.spin_persist.setSingleStep(0.05)
        self.spin_persist.setValue(0.70); self.spin_persist.setFixedWidth(62)
        cl.addWidget(self.spin_persist)
        cl.addStretch()
        bl.addWidget(cfg_row)

        self._body.setVisible(False)
        outer.addWidget(self._body)
        self._n_summary = "N=0"

    def _toggle(self, checked: bool):
        self._expanded = checked
        self._update_header()
        self._body.setVisible(checked)

    def _update_header(self):
        arrow = "▼" if self._expanded else "▶"
        self._hdr.setText(f"{arrow} Signal Convergence  —  {self._n_summary}")

    def _restyle(self):
        if _is_day_mode:
            self._hdr.setStyleSheet("")
            self._help_btn.setStyleSheet("")
            return
        self._hdr.setStyleSheet(f"""
            QPushButton {{
                text-align:left; padding:4px 8px;
                background:{DARK_PANEL}; color:{TEXT};
                border:1px solid {DARK_BORDER}; border-radius:3px; font-size:11pt;
            }}
            QPushButton:checked {{ color:{ACCENT}; }}
        """)
        self._help_btn.setStyleSheet(f"color:{TEXT_HI}; font-size:12pt; border:none;")

    def refresh(self, session: SessionData, cont_mask):
        sigma = float(self.spin_sigma.value())
        pers  = self.spin_persist.value()
        self._canvas.refresh(session, cont_mask, sigma, pers)
        wf = session.welford
        n = wf.n if wf else 0
        self._n_summary = f"N={n}"
        self._update_header()

    def set_xrange(self, x_min: float, x_max: float):
        self._canvas.set_xrange(x_min, x_max)

    def reset_xrange(self):
        self._canvas.reset_xrange()


# ── SNR sparkline panel ───────────────────────────────────────────────────────
class SNRSparklinePanel(QWidget):
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)

        self._expanded = False
        self._hdr = QPushButton("▶ Cont. SNR vs Frame  —  SNR: —")
        self._hdr.setCheckable(True)
        self._hdr.setStyleSheet(f"""
            QPushButton {{
                text-align:left; padding:4px 8px;
                background:{DARK_PANEL}; color:{TEXT};
                border:1px solid {DARK_BORDER}; border-radius:3px;
                font-size:11pt;
            }}
            QPushButton:checked {{ color:{ACCENT}; }}
        """)
        self._hdr.toggled.connect(self._toggle)
        hdr_row = QWidget()
        hl = QHBoxLayout(hdr_row)
        hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(0)
        hl.addWidget(self._hdr, stretch=1)
        self._help_btn = HelpButton(HELP["sparkline"])
        hl.addWidget(self._help_btn)
        outer.addWidget(hdr_row)

        self._body = QWidget()
        bl = QVBoxLayout(self._body)
        bl.setContentsMargins(4, 2, 4, 2)
        bl.setSpacing(3)

        self._canvas = SNRSparklineCanvas()
        bl.addWidget(self._canvas)

        cfg_row = QWidget()
        cl = QHBoxLayout(cfg_row)
        cl.setContentsMargins(0, 0, 0, 0); cl.setSpacing(8)
        cl.addWidget(QLabel("SNR target:"))
        self.spin_snr_tgt = QSpinBox()
        self.spin_snr_tgt.setRange(0, 9999); self.spin_snr_tgt.setValue(0)
        self.spin_snr_tgt.setFixedWidth(65)
        self.spin_snr_tgt.setToolTip("0 = disabled")
        cl.addWidget(self.spin_snr_tgt)
        cl.addStretch()
        bl.addWidget(cfg_row)

        self._body.setVisible(False)
        outer.addWidget(self._body)
        self._snr_summary = "SNR: —"

    def _toggle(self, checked: bool):
        self._expanded = checked
        self._update_header()
        self._body.setVisible(checked)

    def _update_header(self):
        arrow = "▼" if self._expanded else "▶"
        self._hdr.setText(f"{arrow} Cont. SNR vs Frame  —  {self._snr_summary}")

    def _restyle(self):
        if _is_day_mode:
            self._hdr.setStyleSheet("")
            self._help_btn.setStyleSheet("")
            return
        self._hdr.setStyleSheet(f"""
            QPushButton {{
                text-align:left; padding:4px 8px;
                background:{DARK_PANEL}; color:{TEXT};
                border:1px solid {DARK_BORDER}; border-radius:3px; font-size:11pt;
            }}
            QPushButton:checked {{ color:{ACCENT}; }}
        """)
        self._help_btn.setStyleSheet(f"color:{TEXT_HI}; font-size:12pt; border:none;")

    def refresh(self, session: SessionData):
        tgt = float(self.spin_snr_tgt.value())
        self._canvas.refresh(session, tgt)
        snr_h = session.snr_history
        n = session.welford.n if session.welford else 0
        if snr_h and n >= 2:
            self._snr_summary = f"SNR: {snr_h[-1]:.1f}  N={n}"
        else:
            self._snr_summary = f"SNR: —  N={n}"
        self._update_header()


# ── Frame manager panel ───────────────────────────────────────────────────────
class FrameManagerPanel(QWidget):
    recompute_requested = pyqtSignal()
    file_selected       = pyqtSignal(str)   # full filepath when user clicks a row

    _COL_HEADERS = ["#", "File", "Peak ADU", "Cont SNR", "FWHM", "Status", "Include"]

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)

        # ── collapsible header button ─────────────────────────────────────────
        self._expanded = False
        self._hdr = QPushButton("▶ Frame Manager  —  0 / 0 frames,  0 flagged")
        self._hdr.setCheckable(True)
        self._hdr.setStyleSheet(f"""
            QPushButton {{
                text-align:left; padding:4px 8px;
                background:{DARK_PANEL}; color:{TEXT};
                border:1px solid {DARK_BORDER}; border-radius:3px;
                font-size:11pt;
            }}
            QPushButton:checked {{ color:{ACCENT}; }}
        """)
        self._hdr.toggled.connect(self._toggle)
        outer.addWidget(self._hdr)

        # ── auto-flag config row ──────────────────────────────────────────────
        self._cfg_widget = QWidget()
        cl = QHBoxLayout(self._cfg_widget)
        cl.setContentsMargins(4, 2, 4, 2); cl.setSpacing(10)
        self.chk_snr  = QCheckBox("Low SNR")
        self.chk_fwhm = QCheckBox("High FWHM")
        self.chk_sat  = QCheckBox("Saturated")
        self.chk_cont = QCheckBox("< 10 cont. cols")
        for chk in (self.chk_snr, self.chk_fwhm, self.chk_sat, self.chk_cont):
            chk.setChecked(True)
            cl.addWidget(chk)
        btn_recomp = QPushButton("Recompute All")
        btn_recomp.setFixedWidth(120)
        btn_recomp.clicked.connect(self.recompute_requested.emit)
        cl.addWidget(btn_recomp)
        cl.addStretch()
        self._cfg_widget.setVisible(False)
        outer.addWidget(self._cfg_widget)

        # ── frame table ───────────────────────────────────────────────────────
        self._tbl_widget = QWidget()
        tl = QVBoxLayout(self._tbl_widget)
        tl.setContentsMargins(0, 0, 0, 0)
        self._tbl = QTableWidget()
        self._tbl.setColumnCount(len(self._COL_HEADERS))
        self._tbl.setHorizontalHeaderLabels(self._COL_HEADERS)
        self._tbl.setStyleSheet(f"""
            QTableWidget {{
                background:{DARK_PANEL}; color:{TEXT};
                gridline-color:{DARK_BORDER}; font-size:10pt;
                border:1px solid {DARK_BORDER};
            }}
            QHeaderView::section {{
                background:{DARK_BG}; color:{TEXT_HI};
                border:1px solid {DARK_BORDER}; padding:2px; font-size:10pt;
            }}
            QTableWidget::item:selected {{ background:{NIGHT_PALETTE["_SEL_BG"]}; color:{ACCENT}; }}
        """)
        self._tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setFixedHeight(190)
        self._tbl.itemChanged.connect(self._on_item_changed)
        self._tbl.cellClicked.connect(self._on_cell_clicked)
        tl.addWidget(self._tbl)
        self._tbl_widget.setVisible(False)
        outer.addWidget(self._tbl_widget)

        self._session: SessionData | None = None
        self._updating = False

    def _toggle(self, checked: bool):
        self._expanded = checked
        arrow = "▼" if checked else "▶"
        txt = self._hdr.text()
        self._hdr.setText(arrow + txt[1:])
        self._cfg_widget.setVisible(checked)
        self._tbl_widget.setVisible(checked)

    def _on_item_changed(self, item: QTableWidgetItem):
        if self._updating or self._session is None:
            return
        if item.column() != self._COL_HEADERS.index("Include"):
            return
        row = item.row()
        if row >= len(self._session.records):
            return
        rec = self._session.records[row]
        include = item.checkState() == Qt.CheckState.Checked
        if include:
            if rec.inclusion == "excluded":
                rec.inclusion = "flagged" if rec.flag_reasons else "included"
        else:
            if rec.inclusion == "flagged":
                rec.user_kept = False
            rec.inclusion = "excluded"
        self.recompute_requested.emit()

    def _on_cell_clicked(self, row: int, col: int):
        if col == 6 or self._session is None or self._updating:
            return
        if row >= len(self._session.records):
            return
        fp = self._session.records[row].filepath
        if fp:
            self.file_selected.emit(fp)

    def refresh(self, session: SessionData):
        self._session = session
        n_inc = session.n_included
        n_tot = len(session.records)
        n_flg = session.n_flagged
        arrow = "▼" if self._expanded else "▶"
        self._hdr.setText(
            f"{arrow} Frame Manager  —  {n_inc} / {n_tot} frames,  {n_flg} flagged")

        if not self._expanded:
            return

        self._updating = True
        try:
            self._tbl.setRowCount(n_tot)
            for row, rec in enumerate(session.records):
                def _cell(text: str, color: str = TEXT) -> QTableWidgetItem:
                    it = QTableWidgetItem(text)
                    it.setForeground(QColor(color))
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    return it

                if rec.inclusion == "excluded":
                    row_bg = QColor("#ffdddd" if _is_day_mode else "#200000")
                elif rec.inclusion == "flagged" and not rec.user_kept:
                    row_bg = QColor("#fff8e1" if _is_day_mode else "#1a1200")
                else:
                    row_bg = QColor(DARK_PANEL)

                snr_txt  = f"{rec.continuum_snr:.1f}" if rec.continuum_snr is not None else "—"
                fwhm_txt = (f"{rec.fwhm_px:.1f}" + ("" if rec.fwhm_reliable else "?")
                            if rec.fwhm_px is not None else "—")
                if rec.inclusion == "excluded":
                    st_txt, st_col = "Excluded", WARN
                elif rec.inclusion == "flagged":
                    reason = rec.flag_reasons[0] if rec.flag_reasons else ""
                    st_txt = ("Flagged (kept): " if rec.user_kept else "Flagged: ") + reason
                    st_col = ACCENT
                else:
                    st_txt, st_col = "OK", TEXT_DIM

                cells = [
                    _cell(str(rec.frame_number)),
                    _cell(rec.filename[:22]),
                    _cell(f"{rec.peak_adu:.0f}"),
                    _cell(snr_txt),
                    _cell(fwhm_txt),
                    _cell(st_txt, color=st_col),
                ]
                for col, it in enumerate(cells):
                    it.setBackground(row_bg)
                    self._tbl.setItem(row, col, it)

                chk_it = QTableWidgetItem()
                chk_it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                chk_it.setCheckState(
                    Qt.CheckState.Checked if rec.inclusion != "excluded"
                    else Qt.CheckState.Unchecked)
                chk_it.setBackground(row_bg)
                self._tbl.setItem(row, 6, chk_it)

            self._tbl.scrollToBottom()
            self._tbl.resizeColumnsToContents()
        finally:
            self._updating = False

    def autoflag_cfg(self) -> dict:
        return {
            "autoflag_snr_on":       self.chk_snr.isChecked(),
            "autoflag_fwhm_on":      self.chk_fwhm.isChecked(),
            "autoflag_sat_on":       self.chk_sat.isChecked(),
            "autoflag_continuum_on": self.chk_cont.isChecked(),
        }

    def _restyle(self):
        if _is_day_mode:
            self._hdr.setStyleSheet("")
            self._tbl.setStyleSheet("")
            return
        self._hdr.setStyleSheet(f"""
            QPushButton {{
                text-align:left; padding:4px 8px;
                background:{DARK_PANEL}; color:{TEXT};
                border:1px solid {DARK_BORDER}; border-radius:3px; font-size:11pt;
            }}
            QPushButton:checked {{ color:{ACCENT}; }}
        """)
        self._tbl.setStyleSheet(f"""
            QTableWidget {{
                background:{DARK_PANEL}; color:{TEXT};
                gridline-color:{DARK_BORDER}; font-size:10pt;
                border:1px solid {DARK_BORDER};
            }}
            QHeaderView::section {{
                background:{DARK_BG}; color:{TEXT_HI};
                border:1px solid {DARK_BORDER}; padding:2px; font-size:10pt;
            }}
            QTableWidget::item:selected {{ background:{_cur_pal["_SEL_BG"]}; color:{ACCENT}; }}
        """)


# ── Logbook widget ────────────────────────────────────────────────────────────
class LogbookWidget(QWidget):
    """Notepad-style text area; auto-saves to logbook_<Target>.txt in the watch folder."""

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._edit = QPlainTextEdit()
        self._edit.setStyleSheet(f"""
            QPlainTextEdit {{
                background:{DARK_PANEL}; color:{TEXT};
                border:none; font-size:10pt;
                font-family: Consolas, monospace;
            }}
        """)
        self._edit.setPlaceholderText("Session notes…")
        self._edit.setMinimumHeight(70)
        self._edit.textChanged.connect(self._schedule_save)
        lay.addWidget(self._edit)

        self._path: Path | None = None
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self._do_save)

    def set_target(self, folder: str, obj_name: str):
        self._do_save()
        if not folder or not obj_name:
            return
        safe = "".join(c for c in obj_name if c.isalnum() or c in "-_.")
        if not safe:
            safe = "unknown"
        new_path = Path(folder) / f"logbook_{safe}.txt"
        if new_path == self._path:
            return
        self._path = new_path
        if self._path.exists():
            self._edit.blockSignals(True)
            self._edit.setPlainText(self._path.read_text(encoding="utf-8"))
            self._edit.blockSignals(False)
        else:
            from datetime import datetime
            header = f"# {datetime.now().strftime('%Y-%m-%d %H:%M')}  Target: {obj_name}\n"
            self._edit.blockSignals(True)
            self._edit.setPlainText(header)
            self._edit.blockSignals(False)
            self._do_save()

    def _schedule_save(self):
        if self._path is not None:
            self._timer.start()

    def _do_save(self):
        self._timer.stop()
        if self._path is None:
            return
        try:
            self._path.write_text(self._edit.toPlainText(), encoding="utf-8")
        except Exception as e:
            print(f"Logbook save error: {e}")

    def flush(self):
        self._do_save()

    def _restyle(self):
        if _is_day_mode:
            self._edit.setStyleSheet("")
            return
        self._edit.setStyleSheet(f"""
            QPlainTextEdit {{
                background:{DARK_PANEL}; color:{TEXT};
                border:none; font-size:10pt;
                font-family: Consolas, monospace;
            }}
        """)


# ── Session monitor widget (holds all four panels) ────────────────────────────
class SessionMonitorWidget(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(5)

        self._scroll = QScrollArea()
        scroll = self._scroll
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea {{ border:none; background:{DARK_BG}; }}"
            f"QScrollBar:vertical {{ background:{DARK_PANEL}; width:10px; border:none; }}"
            f"QScrollBar::handle:vertical {{ background:{DARK_BORDER}; "
            f"border-radius:4px; min-height:20px; }}"
        )
        self._container = QWidget()
        container = self._container
        container.setStyleSheet(f"background:{DARK_BG};")
        vl = QVBoxLayout(container)
        vl.setContentsMargins(0, 0, 4, 0)
        vl.setSpacing(3)

        self.fwhm_panel = FWHMPanel()
        self.conv_panel = ConvergencePanel()
        self.snr_panel  = SNRSparklinePanel()
        self.frame_mgr  = FrameManagerPanel()
        vl.addWidget(self.fwhm_panel)
        vl.addWidget(self.conv_panel)
        vl.addWidget(self.snr_panel)
        vl.addWidget(self.frame_mgr)
        vl.addStretch()
        scroll.setWidget(container)
        lay.addWidget(scroll, stretch=1)

    def _restyle(self):
        if _is_day_mode:
            self._scroll.setStyleSheet("")
            self._container.setStyleSheet("")
            return
        self._scroll.setStyleSheet(
            f"QScrollArea {{ border:none; background:{DARK_BG}; }}"
            f"QScrollBar:vertical {{ background:{DARK_PANEL}; width:10px; border:none; }}"
            f"QScrollBar::handle:vertical {{ background:{DARK_BORDER}; "
            f"border-radius:4px; min-height:20px; }}"
        )
        self._container.setStyleSheet(f"background:{DARK_BG};")

    def refresh_all(self, session: SessionData, cont_mask):
        self.fwhm_panel.refresh(session)
        self.conv_panel.refresh(session, cont_mask)
        self.snr_panel.refresh(session)
        self.frame_mgr.refresh(session)

    @property
    def flatness_threshold(self) -> float:
        return self.fwhm_panel.spin_flat.value()


# ── Main window ────────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg         = load_config()
        self.fits_data   = None
        self.watcher: FolderWatcher | None = None
        self._hold       = False
        self._busy       = False
        self._gain_on    = self.cfg.get("gain_advice_on", False)
        self._spec       = None
        self._bg         = None
        self._n_target   = 1
        self._cur_file   = ""
        self.session_data: SessionData       = SessionData()
        self._last_cont_mask: np.ndarray | None = None
        self._step_files: list[str] = []
        self._step_idx:   int       = 0
        self._step_timer: QTimer | None = None

        self.setWindowTitle("Spectro Inspector")
        self.setMinimumSize(1200, 760)
        QApplication.instance().setStyleSheet(STYLE)
        self._apply_palette()
        self._build_ui()
        self._load_cfg_to_ui()

        if self.cfg.get("watch_folder"):
            self._start_watcher(self.cfg["watch_folder"])

    def _apply_palette(self):
        app = QApplication.instance()
        if _is_day_mode:
            app.setPalette(app.style().standardPalette())
            return
        p = QPalette()
        p.setColor(QPalette.ColorRole.Window,          QColor(DARK_BG))
        p.setColor(QPalette.ColorRole.WindowText,      QColor(TEXT))
        p.setColor(QPalette.ColorRole.Base,            QColor(DARK_PANEL))
        p.setColor(QPalette.ColorRole.AlternateBase,   QColor(DARK_BG))
        p.setColor(QPalette.ColorRole.Text,            QColor(TEXT))
        p.setColor(QPalette.ColorRole.Button,          QColor(_cur_pal["_BTN_BG"]))
        p.setColor(QPalette.ColorRole.ButtonText,      QColor(TEXT_HI))
        p.setColor(QPalette.ColorRole.Highlight,       QColor(_cur_pal["_SEL_BG"]))
        p.setColor(QPalette.ColorRole.HighlightedText, QColor(ACCENT))
        app.setPalette(p)

    def _build_ui(self):
        root = QWidget()
        rl = QVBoxLayout(root)
        rl.setContentsMargins(6, 6, 6, 2)
        rl.setSpacing(4)
        self.setCentralWidget(root)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        rl.addWidget(splitter, stretch=1)

        # ── LEFT: image ──────────────────────────────────────────────────────
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 4, 0)
        ll.setSpacing(4)

        img_grp, img_lay = section_box("Latest FITS Image", "image")
        self.img_canvas = ImageCanvas()
        self.img_canvas.line_released.connect(self._on_lines_released)
        self.img_canvas.zoom_x_changed.connect(self._on_zoom_x_changed)
        self.img_canvas.zoom_reset_sig.connect(self._on_zoom_reset_sync)
        img_lay.addWidget(self.img_canvas)
        ll.addWidget(img_grp, stretch=1)

        reg_grp, reg_lay = section_box(
            "Extraction Regions", "regions")

        # Compact toolbar: zoom + stretch on one line
        toolbar = QWidget()
        tl = QHBoxLayout(toolbar)
        tl.setContentsMargins(0, 0, 0, 2); tl.setSpacing(6)
        self.btn_zoom = QPushButton("⊕ Zoom")
        self.btn_zoom.setCheckable(True)
        self.btn_zoom.setFixedWidth(78)
        self.btn_zoom.setToolTip("Click and drag a rectangle on the image to zoom in")
        self.btn_zoom.toggled.connect(self._on_zoom_toggle)
        self.btn_reset_zoom = QPushButton("↺ Reset")
        self.btn_reset_zoom.setFixedWidth(78)
        self.btn_reset_zoom.setToolTip("Restore full image and spectrum view")
        self.btn_reset_zoom.clicked.connect(self._on_zoom_reset)
        tl.addWidget(self.btn_zoom)
        tl.addWidget(self.btn_reset_zoom)
        stretch_lbl = QLabel("Stretch:")
        stretch_lbl.setStyleSheet(f"color:{TEXT_DIM}; font-size:10pt; border:none;")
        self._stretch_lbl = stretch_lbl
        tl.addWidget(stretch_lbl)
        self.stretch_slider = QSlider(Qt.Orientation.Horizontal)
        self.stretch_slider.setRange(1, 10)
        self.stretch_slider.setFixedWidth(90)
        self.stretch_slider.valueChanged.connect(self._on_stretch)
        tl.addWidget(self.stretch_slider)
        tl.addStretch()
        reg_lay.addWidget(toolbar)

        self.ctrl_target   = RegionControl("TARGET",   TARGET_C)
        self.ctrl_bg_above = RegionControl("BG ABOVE", BG_C)
        self.ctrl_bg_below = RegionControl("BG BELOW", BG_C)
        for ctrl in (self.ctrl_target, self.ctrl_bg_above, self.ctrl_bg_below):
            ctrl.changed.connect(self._on_regions_changed)
            reg_lay.addWidget(ctrl)
        # Bottom left: extraction regions + logbook side by side
        bottom_left = QWidget()
        bll = QHBoxLayout(bottom_left)
        bll.setContentsMargins(0, 0, 0, 0)
        bll.setSpacing(4)
        bll.addWidget(reg_grp)

        log_grp, log_lay = section_box("Logbook")
        self.logbook = LogbookWidget()
        log_lay.addWidget(self.logbook)
        bll.addWidget(log_grp, stretch=1)
        ll.addWidget(bottom_left)

        # ── RIGHT: tabbed panel ────────────────────────────────────────────────
        right = QWidget()
        rl2 = QVBoxLayout(right)
        rl2.setContentsMargins(4, 0, 0, 0)
        rl2.setSpacing(0)

        tabs = QTabWidget()
        self._tabs_widget = tabs
        tabs.setStyleSheet(f"""
            QTabWidget::pane  {{ border: 1px solid {DARK_BORDER}; }}
            QTabBar::tab      {{ background:{DARK_PANEL}; color:{TEXT};
                                 padding:4px 14px; border:1px solid {DARK_BORDER};
                                 font-size:11pt; }}
            QTabBar::tab:selected {{ background:{NIGHT_PALETTE["_SEL_BG"]}; color:{TEXT_HI}; }}
            QTabBar::tab:hover    {{ background:{NIGHT_PALETTE["_SEL_BG"]}; }}
        """)

        # Tab 0: Spectrum & Advisory
        spec_tab = QWidget()
        st_lay = QVBoxLayout(spec_tab)
        st_lay.setContentsMargins(0, 4, 0, 0)
        st_lay.setSpacing(4)

        spec_grp, spec_lay = section_box("Extracted Spectrum", "spectrum")
        self.spec_canvas = SpectrumCanvas()
        spec_lay.addWidget(self.spec_canvas)

        opt_row = QWidget()
        ol = QHBoxLayout(opt_row)
        ol.setContentsMargins(0, 0, 0, 0)
        ol.setSpacing(8)
        self.chk_norm = QCheckBox("Normalize to peak")
        snr_row = QWidget()
        snr_rl = QHBoxLayout(snr_row)
        snr_rl.setContentsMargins(0, 0, 0, 0)
        snr_rl.setSpacing(2)
        self.chk_snr = QCheckBox("Show SNR curve")
        snr_rl.addWidget(self.chk_snr)
        self._snr_help_btn = HelpButton(HELP["snr"])
        snr_rl.addWidget(self._snr_help_btn)
        self.chk_norm.toggled.connect(self._on_options)
        self.chk_snr.toggled.connect(self._on_options)
        ol.addWidget(self.chk_norm)
        ol.addWidget(snr_row)
        ol.addStretch()
        spec_lay.addWidget(opt_row)
        st_lay.addWidget(spec_grp, stretch=1)

        self.advisory = AdvisoryPanel()
        st_lay.addWidget(self.advisory)
        tabs.addTab(spec_tab, "Spectrum")

        # Tab 1: Session Monitor
        self.session_monitor = SessionMonitorWidget()
        self.session_monitor.frame_mgr.recompute_requested.connect(self._on_recompute)
        self.session_monitor.frame_mgr.file_selected.connect(self._on_frame_selected)
        tabs.addTab(self.session_monitor, "Session Monitor")

        rl2.addWidget(tabs, stretch=1)
        splitter.addWidget(left)
        splitter.addWidget(right)

        # ── BOTTOM CONTROLS BAR ───────────────────────────────────────────────
        bottom = QFrame()
        self._bottom_bar = bottom
        bottom.setStyleSheet(
            f"QFrame {{ background:{DARK_PANEL}; border-top:1px solid {DARK_BORDER}; }}")
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(8, 6, 8, 6)
        bl.setSpacing(10)

        self.btn_folder = QPushButton("Select Folder")
        self.btn_folder.clicked.connect(self._select_folder)

        self.btn_step = QPushButton("Step Through Files")
        self.btn_step.setToolTip(
            "Load all existing FITS files one-by-one (3 s delay), then switch to live polling")
        self.btn_step.clicked.connect(self._toggle_step_through)
        self.btn_step.setEnabled(bool(self.cfg.get("watch_folder")))

        self.lbl_folder = QLabel("No folder selected")
        self.lbl_folder.setStyleSheet(f"color:{TEXT_DIM}; font-size:{F_SM};")
        self.lbl_folder.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet(f"QFrame {{ color:{DARK_BORDER}; max-width:1px; }}")

        sci_lbl = QLabel("Science Image:")
        sci_lbl.setStyleSheet(f"color:{TEXT_DIM}; font-size:11pt;")
        self._sci_lbl = sci_lbl
        self.radio_latest = QRadioButton("Display Latest")
        self.radio_hold   = QRadioButton("Keep Current")
        self.radio_latest.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.radio_latest)
        grp.addButton(self.radio_hold)
        self.radio_latest.toggled.connect(
            lambda chk: setattr(self, "_hold", not chk))

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setStyleSheet(f"QFrame {{ color:{DARK_BORDER}; max-width:1px; }}")

        self.btn_gain = QPushButton("Gain Advice: OFF")
        self._vline_seps = [sep1, sep2]
        self.btn_gain.setCheckable(True)
        self.btn_gain.setChecked(self._gain_on)
        self.btn_gain.setFixedWidth(190)
        self.btn_gain.toggled.connect(self._on_gain_toggle)
        self._update_gain_btn_label()

        sep3 = QFrame()
        sep3.setFrameShape(QFrame.Shape.VLine)
        sep3.setStyleSheet(f"QFrame {{ color:{DARK_BORDER}; max-width:1px; }}")
        self._vline_seps.append(sep3)

        self.btn_theme = QPushButton("Day Mode")
        self.btn_theme.setCheckable(True)
        self.btn_theme.setFixedWidth(110)
        self.btn_theme.setToolTip("Switch between night-vision (red) and day (blue) colour schemes")
        self.btn_theme.toggled.connect(self._on_theme_toggle)

        for w in (self.btn_folder, self.btn_step, self.lbl_folder, sep1,
                  sci_lbl, self.radio_latest, self.radio_hold, sep2,
                  self.btn_gain, sep3, self.btn_theme):
            bl.addWidget(w)

        rl.addWidget(bottom)

        # ── Status bar ────────────────────────────────────────────────────────
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.sb_file  = QLabel("No file loaded")
        self.sb_info  = QLabel("")
        self.sb_count = QLabel("")
        self.sb_file.setStyleSheet(f"font-size:{F_SM};")
        self.sb_info.setStyleSheet(f"color:{TEXT_DIM}; font-size:{F_SM};")
        self.sb_count.setStyleSheet(f"color:{TEXT_DIM}; font-size:{F_SM};")
        sb.addWidget(self.sb_file, 2)
        sb.addWidget(self.sb_info, 2)
        sb.addPermanentWidget(self.sb_count)

    @staticmethod
    def _file_info_text(d: dict) -> str:
        parts = []
        if d["exptime"]     is not None: parts.append(f"Exp: {float(d['exptime']):.1f} s")
        if d["gain_slider"] is not None: parts.append(f"Gain: {d['gain_slider']}")
        parts.append(f"{d['bitpix']}-bit")
        if d["camera"] != "Unknown":     parts.append(d["camera"])
        if d["object"]:                  parts.append(d["object"])
        return "   |   ".join(parts)

    # ── config <-> UI ─────────────────────────────────────────────────────────
    def _load_cfg_to_ui(self):
        self.ctrl_target.set_values(
            self.cfg["target_y_start"], self.cfg["target_y_end"])
        self.ctrl_bg_above.set_values(
            self.cfg["bg_above_y_start"], self.cfg["bg_above_y_end"])
        self.ctrl_bg_below.set_values(
            self.cfg["bg_below_y_start"], self.cfg["bg_below_y_end"])
        self.stretch_slider.setValue(self.cfg.get("stretch_value", 3))
        self.chk_norm.setChecked(self.cfg.get("normalize_spectrum", False))
        self.chk_snr.setChecked(self.cfg.get("show_snr", True))
        if self.cfg.get("watch_folder"):
            self.lbl_folder.setText(self.cfg["watch_folder"])

    def _ui_to_cfg(self):
        self.cfg["target_y_start"],   self.cfg["target_y_end"]   = \
            self.ctrl_target.get_values()
        self.cfg["bg_above_y_start"], self.cfg["bg_above_y_end"] = \
            self.ctrl_bg_above.get_values()
        self.cfg["bg_below_y_start"], self.cfg["bg_below_y_end"] = \
            self.ctrl_bg_below.get_values()
        self.cfg["stretch_value"]      = self.stretch_slider.value()
        self.cfg["normalize_spectrum"] = self.chk_norm.isChecked()
        self.cfg["show_snr"]           = self.chk_snr.isChecked()
        self.cfg["gain_advice_on"]     = self._gain_on

    def _spinboxes_from_canvas(self):
        r = self.img_canvas.get_region()
        self.ctrl_target.set_values(r["tgt_top"], r["tgt_bot"])
        self.ctrl_bg_above.set_values(r["bga_top"], r["bga_bot"])
        self.ctrl_bg_below.set_values(r["bgb_top"], r["bgb_bot"])

    def _cfg_from_canvas(self):
        self.img_canvas.region_to_cfg(self.cfg)
        self.cfg["stretch_value"]      = self.stretch_slider.value()
        self.cfg["normalize_spectrum"] = self.chk_norm.isChecked()
        self.cfg["show_snr"]           = self.chk_snr.isChecked()

    def _update_gain_btn_label(self):
        on = self.btn_gain.isChecked()
        self.btn_gain.setText(f"Gain Advice: {'ON' if on else 'OFF'}")

    # ── folder / watcher ─────────────────────────────────────────────────────
    def _select_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select FITS folder", self.cfg.get("watch_folder", ""))
        if folder:
            self.cfg["watch_folder"] = folder
            self.lbl_folder.setText(folder)
            save_config(self.cfg)
            self.btn_step.setEnabled(True)
            self._start_watcher(folder)

    def _start_watcher(self, folder):
        if self.watcher:
            self.watcher.stop()
            self.watcher.wait(600)

        # Always start a fresh session when changing / re-opening a folder
        self.session_data      = SessionData()
        self._last_cont_mask   = None

        self.watcher = FolderWatcher(
            folder, self.cfg.get("poll_interval_ms", 2000))
        self.watcher.new_file_found.connect(self._on_new_file)
        self.watcher.start()
        self.sb_count.setText(f"{self.watcher.count()} file(s)")

        if self.watcher.latest():
            self._load_file(self.watcher.latest())
        else:
            self._clear_display()

    def _clear_display(self):
        """Reset all panels to empty state (no FITS data)."""
        self.fits_data  = None
        self._spec      = None
        self._bg        = None
        self._n_target  = 1
        self._cur_file  = ""
        self.setWindowTitle("Spectro Inspector")
        self.sb_file.setText("No file loaded")
        self.sb_info.setText("")
        self._refresh_all()
        self.session_monitor.refresh_all(self.session_data, self._last_cont_mask)

    # ── step-through replay ───────────────────────────────────────────────────
    def _toggle_step_through(self):
        if self._step_files:
            self._stop_step_through()
        else:
            self._start_step_through()

    def _start_step_through(self):
        folder = self.cfg.get("watch_folder", "")
        if not folder:
            return

        # Stop live watcher while replaying
        if self.watcher:
            self.watcher.stop()
            self.watcher.wait(600)
            self.watcher = None

        # Fresh session so replay builds analytics from scratch
        self.session_data    = SessionData()
        self._last_cont_mask = None
        self._clear_display()

        p = Path(folder)
        seen: set[str] = set()
        files: list[Path] = []
        for pat in ("*.fits", "*.fit", "*.FITS", "*.FIT"):
            for f in p.glob(pat):
                key = str(f.resolve()).lower()
                if key not in seen:
                    seen.add(key)
                    files.append(f)
        files.sort(key=lambda f: f.stat().st_mtime)

        if not files:
            self._start_watcher(folder)
            return

        self._step_files = [str(f) for f in files]
        self._step_idx   = 0

        if self._step_timer is None:
            self._step_timer = QTimer(self)
            self._step_timer.setSingleShot(True)
            self._step_timer.timeout.connect(self._do_step)

        self.btn_step.setText("Stop Replay")
        self.btn_folder.setEnabled(False)
        self._do_step()

    def _do_step(self):
        if self._step_idx >= len(self._step_files):
            self._finish_step_through()
            return

        path = self._step_files[self._step_idx]
        self._step_idx += 1
        total = len(self._step_files)
        self.sb_count.setText(f"Stepping: {self._step_idx} / {total}")
        self._load_file(path)

        if self._step_idx < total:
            self._step_timer.start(3000)
        else:
            self._finish_step_through()

    def _finish_step_through(self):
        self._step_files = []
        self._step_idx   = 0
        self.btn_step.setText("Step Through Files")
        self.btn_folder.setEnabled(True)

        folder = self.cfg.get("watch_folder", "")
        if folder:
            self.watcher = FolderWatcher(
                folder, self.cfg.get("poll_interval_ms", 2000))
            self.watcher.new_file_found.connect(self._on_new_file)
            self.watcher.start()
            self.sb_count.setText(f"{self.watcher.count()} file(s) — live")

    def _stop_step_through(self):
        if self._step_timer:
            self._step_timer.stop()
        self._finish_step_through()

    def _on_new_file(self, path):
        if self.watcher:
            self.sb_count.setText(f"{self.watcher.count()} file(s)")
        if not self._hold:
            self._load_file(path)

    # ── file loading ──────────────────────────────────────────────────────────
    def _load_file(self, path):
        d = load_fits(path)
        if d is None:
            self.sb_file.setText(f"Failed: {Path(path).name}")
            return
        self.fits_data = d
        self._cur_file = d["filename"]
        self.setWindowTitle(f"Spectro Inspector  —  {self._cur_file}")

        gs = d.get("gain_slider")
        if gs is not None:
            e_adu, rn_cam, _ = interp_gain(float(gs))
            self.cfg["conversion_gain"] = round(e_adu, 4)
            self.cfg["read_noise"]      = round(rn_cam, 2)

        obj = d.get("object", "")
        folder = self.cfg.get("watch_folder", "")
        if obj and folder:
            self.logbook.set_target(folder, obj)

        self._refresh_all()
        self._process_session_frame()

        self.sb_file.setText(d["filename"])
        self.sb_info.setText(self._file_info_text(d))

    # ── refresh ───────────────────────────────────────────────────────────────
    def _refresh_all(self):
        if self._busy: return
        self._busy = True
        try:
            self._ui_to_cfg()
            self.img_canvas.refresh(self.fits_data, self.cfg, self.stretch_slider.value())
            self._refresh_spec_advisory()
        finally:
            self._busy = False

    def _refresh_spec_advisory(self):
        res = self.spec_canvas.refresh(
            self.fits_data, self.cfg,
            self.chk_snr.isChecked(), self.chk_norm.isChecked())
        if res is not None:
            _, self._spec, self._bg, self._n_target = res
        self.advisory.refresh_data(
            self.fits_data, self.cfg,
            self._spec, self._bg, self._n_target,
            gain_on=self._gain_on)

    # ── signal handlers ───────────────────────────────────────────────────────
    def _on_lines_released(self):
        self._cfg_from_canvas()
        self._spinboxes_from_canvas()
        save_config(self.cfg)
        self._refresh_spec_advisory()

    def _on_regions_changed(self):
        self._ui_to_cfg()
        save_config(self.cfg)
        self._refresh_all()

    def _on_stretch(self):
        self._ui_to_cfg()
        save_config(self.cfg)
        self.img_canvas.refresh(self.fits_data, self.cfg, self.stretch_slider.value())

    def _on_options(self):
        self._ui_to_cfg()
        save_config(self.cfg)
        self._refresh_spec_advisory()

    def _on_gain_toggle(self, checked):
        self._gain_on = checked
        self._update_gain_btn_label()
        self.cfg["gain_advice_on"] = checked
        save_config(self.cfg)
        self._refresh_spec_advisory()

    def _on_zoom_toggle(self, checked):
        self.img_canvas.set_zoom_mode(checked)

    def _on_zoom_reset(self):
        self.btn_zoom.setChecked(False)
        self.img_canvas.reset_zoom()

    def _on_zoom_x_changed(self, x_min: float, x_max: float):
        self.spec_canvas.set_xrange(x_min, x_max, self._spec)
        self.session_monitor.conv_panel.set_xrange(x_min, x_max)

    def _on_zoom_reset_sync(self):
        self.spec_canvas.reset_xrange()
        self.session_monitor.conv_panel.reset_xrange()

    # ── session processing ────────────────────────────────────────────────────
    def _process_session_frame(self):
        """Run the current FITS frame through the session analysis pipeline."""
        if self.fits_data is None or self._spec is None:
            return
        cfg  = self.cfg
        data = self.fits_data["data"]
        spec = self._spec

        # Flatness mask — shared filter
        threshold  = self.session_monitor.flatness_threshold
        cont_mask  = compute_flatness_mask(
            spec,
            central_fraction = cfg.get("central_col_fraction", 0.35),
            deriv_window     = int(cfg.get("derivative_window", 7)),
            threshold        = threshold,
        )
        n_cont = int(np.sum(cont_mask))
        self._last_cont_mask = cont_mask

        # Spatial profile + Gaussian FWHM
        y0_prof = cfg.get("bg_above_y_start", 0)
        y1_prof = cfg.get("bg_below_y_end", data.shape[0])
        fwhm, _centroid, reliable = None, None, False
        if n_cont >= 10:
            spatial = _spatial_profile_from_continuum(data, cont_mask, y0_prof, y1_prof)
            if spatial is not None:
                fwhm, _centroid, reliable = fit_gaussian_spatial(
                    spatial,
                    residual_threshold=cfg.get("gaussian_residual_thresh", 0.30),
                )

        # Per-frame continuum SNR (from existing SNR array, averaged over cont cols)
        cont_snr = None
        if n_cont >= 10 and self._bg is not None:
            G   = cfg.get("conversion_gain", 0.022)
            R   = cfg.get("read_noise", 0.8)
            snr_arr = compute_snr(spec, self._bg, self._n_target, G, R)
            cont_snr = float(np.mean(snr_arr[cont_mask]))

        # Build frame record
        h    = data.shape[0]
        y0t  = max(0, cfg["target_y_start"]); y1t = min(h, cfg["target_y_end"])
        peak = float(np.max(data[y0t:y1t, :])) if y1t > y0t else 0.0
        slmt = cfg.get("saturation_threshold", 0.70) * self.fits_data["full_range"]

        rec = FrameRecord(
            frame_number  = len(self.session_data.records) + 1,
            filename      = self.fits_data.get("filename", ""),
            filepath      = self.fits_data.get("filepath", ""),
            timestamp     = self.fits_data.get("date_obs", ""),
            peak_adu      = peak,
            sat_limit     = slmt,
            continuum_snr = cont_snr,
            fwhm_px       = fwhm,
            fwhm_reliable = reliable,
            n_continuum   = n_cont,
        )

        # Merge autoflag cfg from frame manager UI
        af_cfg = {**cfg, **self.session_monitor.frame_mgr.autoflag_cfg()}
        reasons = self.session_data.autoflag_frame(rec, af_cfg)
        if reasons:
            rec.inclusion    = "flagged"
            rec.flag_reasons = reasons

        self.session_data.add_frame(rec, spec, cont_mask)
        self.session_monitor.refresh_all(self.session_data, self._last_cont_mask)

    def _on_recompute(self):
        """Full Welford replay triggered by user exclusion change."""
        self.session_data.recompute()
        self.session_monitor.refresh_all(self.session_data, self._last_cont_mask)

    def _on_frame_selected(self, path: str):
        """Frame Manager row click — show that frame only when in Keep Current mode."""
        if self._hold:
            self._display_file_only(path)

    def _display_file_only(self, path: str):
        """Load a FITS file for display without creating a new session record."""
        d = load_fits(path)
        if d is None:
            return
        self.fits_data = d
        gs = d.get("gain_slider")
        if gs is not None:
            e_adu, rn_cam, _ = interp_gain(float(gs))
            self.cfg["conversion_gain"] = round(e_adu, 4)
            self.cfg["read_noise"]      = round(rn_cam, 2)
        self._refresh_all()
        self.sb_file.setText(f"[viewing] {d['filename']}")
        self.sb_info.setText(self._file_info_text(d))

    def _on_theme_toggle(self, day: bool):
        self.btn_theme.setText("Night Mode" if day else "Day Mode")
        self._switch_theme(day)

    def _switch_theme(self, day: bool):
        global _cur_pal
        _cur_pal = DAY_PALETTE if day else NIGHT_PALETTE
        _apply_palette_vars(_cur_pal)
        QApplication.instance().setStyleSheet(make_style())
        self._apply_palette()

        # Section-box titles, help buttons, group borders, separators
        for lbl in _section_titles:
            lbl.setStyleSheet(
                "" if day else
                f"color:{TEXT_HI}; font-size:{F_TITLE}; font-weight:bold; border:none;")
        for hbtn in _section_help_buttons:
            hbtn.setStyleSheet(
                "" if day else f"color:{TEXT_HI}; font-size:12pt; border:none;")
        self._snr_help_btn.setStyleSheet(
            "" if day else f"color:{TEXT_HI}; font-size:12pt; border:none;")
        for grp in _section_boxes:
            grp.setStyleSheet(
                "" if day else
                f"QGroupBox {{ border:1px solid {DARK_BORDER}; border-radius:4px;"
                f" margin-top:0px; padding-top:2px; }}")
        for sep in _section_seps:
            sep.setStyleSheet(
                "" if day else
                f"QFrame{{background:{DARK_BORDER}; max-height:1px; border:none;}}")

        # Bottom bar and its children
        self._bottom_bar.setStyleSheet(
            "" if day else
            f"QFrame {{ background:{DARK_PANEL}; border-top:1px solid {DARK_BORDER}; }}")
        for sep in self._vline_seps:
            sep.setStyleSheet(
                "" if day else f"QFrame {{ color:{DARK_BORDER}; max-width:1px; }}")
        self.lbl_folder.setStyleSheet(
            "" if day else f"color:{TEXT_DIM}; font-size:{F_SM};")
        self._sci_lbl.setStyleSheet(
            "" if day else f"color:{TEXT_DIM}; font-size:11pt;")

        # Stretch label
        self._stretch_lbl.setStyleSheet(
            "" if day else f"color:{TEXT_DIM}; font-size:10pt; border:none;")

        # Status bar labels
        self.sb_file.setStyleSheet(
            "" if day else f"font-size:{F_SM};")
        self.sb_info.setStyleSheet(
            "" if day else f"color:{TEXT_DIM}; font-size:{F_SM};")
        self.sb_count.setStyleSheet(
            "" if day else f"color:{TEXT_DIM}; font-size:{F_SM};")

        # Tab widget
        self._tabs_widget.setStyleSheet(
            "" if day else f"""
            QTabWidget::pane  {{ border: 1px solid {DARK_BORDER}; }}
            QTabBar::tab      {{ background:{DARK_PANEL}; color:{TEXT};
                                 padding:4px 14px; border:1px solid {DARK_BORDER};
                                 font-size:11pt; }}
            QTabBar::tab:selected {{ background:{NIGHT_PALETTE["_SEL_BG"]}; color:{TEXT_HI}; }}
            QTabBar::tab:hover    {{ background:{NIGHT_PALETTE["_SEL_BG"]}; }}
        """)

        # Region controls (dot/label inline styles)
        for ctrl in (self.ctrl_target, self.ctrl_bg_above, self.ctrl_bg_below):
            ctrl._restyle()

        # Session monitor scroll area and panels
        self.session_monitor._restyle()
        for panel in (self.session_monitor.fwhm_panel,
                      self.session_monitor.conv_panel,
                      self.session_monitor.snr_panel,
                      self.session_monitor.frame_mgr,
                      self.advisory, self.logbook):
            if hasattr(panel, '_restyle'):
                panel._restyle()

        # Refresh matplotlib canvases with new colours
        if self.fits_data is not None:
            self._refresh_all()
            self.session_monitor.refresh_all(self.session_data, self._last_cont_mask)
        else:
            for canvas in (self.img_canvas, self.spec_canvas,
                           self.session_monitor.fwhm_panel._canvas,
                           self.session_monitor.conv_panel._canvas,
                           self.session_monitor.snr_panel._canvas):
                canvas.fig.set_facecolor(DARK_BG)
                for ax in canvas.fig.axes:
                    ax.set_facecolor(DARK_BG)
                    for sp in ax.spines.values():
                        sp.set_edgecolor(DARK_BORDER)
                    ax.tick_params(colors=TEXT, labelsize=8)
                canvas.draw_idle()

    def closeEvent(self, event):
        self._ui_to_cfg()
        save_config(self.cfg)
        self.logbook.flush()
        if self.watcher:
            self.watcher.stop()
            self.watcher.wait(600)
        event.accept()


# ── Entry point ────────────────────────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 11))

    p = QPalette()
    p.setColor(QPalette.ColorRole.Window,          QColor(DARK_BG))
    p.setColor(QPalette.ColorRole.WindowText,      QColor(TEXT))
    p.setColor(QPalette.ColorRole.Base,            QColor(DARK_PANEL))
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor(DARK_BG))
    p.setColor(QPalette.ColorRole.ToolTipBase,     QColor(DARK_PANEL))
    p.setColor(QPalette.ColorRole.ToolTipText,     QColor(TEXT))
    p.setColor(QPalette.ColorRole.Text,            QColor(TEXT))
    p.setColor(QPalette.ColorRole.Button,          QColor(NIGHT_PALETTE["_BTN_BG"]))
    p.setColor(QPalette.ColorRole.ButtonText,      QColor(TEXT_HI))
    p.setColor(QPalette.ColorRole.BrightText,      QColor(ACCENT))
    p.setColor(QPalette.ColorRole.Link,            QColor(ACCENT))
    p.setColor(QPalette.ColorRole.Highlight,       QColor(NIGHT_PALETTE["_SEL_BG"]))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(ACCENT))
    app.setPalette(p)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

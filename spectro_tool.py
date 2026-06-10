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
import fnmatch
import shutil
from pathlib import Path
from dataclasses import dataclass, field

import numpy as np
from datetime import datetime
from scipy.ndimage import rotate
from scipy.signal import find_peaks
from scipy.optimize import curve_fit, minimize

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
        QScrollArea, QLineEdit, QAbstractSpinBox,
        QComboBox, QListWidget,
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
    from matplotlib.ticker import FuncFormatter, MaxNLocator
    from matplotlib.widgets import SpanSelector
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
_arrow_btns_list:      list = []   # all ▲/▼ QPushButtons created by _arrow_btns()
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
QSpinBox, QDoubleSpinBox, QLineEdit {{ background-color:{DARK_PANEL}; color:{ACCENT};
                          border:1px solid {DARK_BORDER}; border-radius:2px;
                          padding:3px; font-size:{F_BASE}; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ width:0px; border:none; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ width:0px; border:none; }}
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


# ── Lamp line database ─────────────────────────────────────────────────────────
LAMP_LINES: dict = {
    "Ne": {
        "label": "Ne — Glowlamp  ⚠ red-only",
        "lines": [
            ("Ne", 5852.48), ("Ne", 6143.06), ("Ne", 6402.25),
            ("Ne", 6678.28), ("Ne", 6929.47), ("Ne", 7032.41),
            ("Ne", 7245.17), ("Ne", 7438.90),
        ],
        "warn": "Ne only: no lines below 5852 Å — blue end uncalibrated",
    },
    "NeXe": {
        "label": "NeXe — Phillips S10",
        "lines": [
            ("Xe", 4213.72), ("Xe", 4843.29), ("Xe", 4916.51),
            ("Xe", 5401.00), ("Ne", 5852.48), ("Ne", 6270.82),
            ("Ne", 6402.25), ("Xe", 6512.83), ("Ne", 6678.28),
            ("Ne", 6929.47), ("Ne", 7032.41), ("Xe", 7119.60),
            ("Ne", 7245.17),
        ],
        "warn": None,
    },
    "ArH": {
        "label": "ArH — Osram ST111",
        "lines": [
            ("Ar", 4200.67), ("Ar", 4764.87), ("H",  4861.33),
            ("H",  6562.80), ("Ar", 6677.28), ("Ar", 6965.43),
            ("Ar", 7383.98), ("Ar", 7635.11),
        ],
        "warn": None,
    },
    "NeArHe": {
        "label": "NeArHe — Relco SC480",
        "lines": [
            ("Ar", 4200.67), ("Ar", 4764.87), ("Ne", 5852.48),
            ("Ne", 6143.06), ("Ne", 6402.25), ("Ar", 6677.28),
            ("Ar", 6965.43), ("Ar", 7147.04), ("Ar", 7383.98),
            ("Ar", 7635.11),
        ],
        "warn": None,
    },
}

STELLAR_LINES: list = [
    ("Hγ",   4340.47),
    ("Hβ",   4861.33),
    ("He I", 5875.61),
    ("Hα",   6562.80),
    ("He I", 6678.15),
    ("He I", 7065.19),
]

WAVE_MIN_DEFAULT = 3500.0
WAVE_MAX_DEFAULT = 8000.0


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
<b>X axis</b>: pixel column — proportional to wavelength (uncalibrated).<br>
<b>Y axis</b>: ADU — fixed 0 to full sensor range (65 535 for 16-bit).<br><br>
• <b>White line</b> — hot-pixel-filtered peak per column: the 2nd-highest
  pixel value across all TARGET rows for each column (rejects single
  hot pixels without clipping real signal).<br>
• <b>Amber line</b> — sky background level: sigma-clipped mean across
  the BG ABOVE and BG BELOW regions per column.<br>
• <b>Dashed red line</b> — linearity limit at 80 % of full ADU range
  (52 428 ADU for a 16-bit sensor). Pixels above this may show
  non-linear detector response.<br>
• <b>Red shading</b> — column runs where the peak pixel exceeds the
  linearity limit.<br><br>
<b>Zoom buttons</b> (below the chart): ⊕ Zoom draws a rubber-band box
to zoom both axes. "Zoom to range" sets the Y scale so the spectrum
peak sits at 80 % of the visible range. ↺ Reset restores full view.
Zoom settings persist across file loads until Reset is clicked.
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
<b>Slit Quality Metrics</b><br><br>
All metrics are plotted as <b>% deviation from the session baseline</b>
(mean of the first 5 valid frames), sharing one y-axis. A flat trace near
0 % means that metric is stable. Toggle each metric with the checkboxes
above the chart.<br><br>

<b>Integrated Flux</b> — Total ADU summed across the extracted 1D spectrum per
frame. Direct measure of starlight throughput through the slit. A sustained
downward drift means the star has moved toward or beyond a slit jaw.<br><br>

<b>Spatial Centroid Y</b> — Flux-weighted centre of the stellar profile in the
cross-dispersion (Y) direction, in pixels. Slow drift indicates the star is
walking across the slit. A sudden jump suggests a guiding disturbance.<br><br>

<b>Profile Asymmetry</b> — Imbalance of flux above vs below the centroid,
plotted as %. Zero = symmetric. Non-zero means the star is being clipped by
one slit jaw. Rising asymmetry + falling flux = early warning of a slit edge.<br><br>

<b>Flux RMS</b> — Rolling standard deviation of Integrated Flux over the last N
frames (set by RMS window spinbox), normalised to session mean flux. Spikes
near a slit edge as seeing fluctuations become amplitude-modulated by the slit
transmission — the quantitative signature of yo-yoing across the edge.<br><br>

<b>FWHM</b> (optional, off by default) — Gaussian width of the spatial profile
in pixels. A focus and seeing quality indicator, <i>not</i> a centering metric.
The Warn% and Alarm% thresholds apply to FWHM when enabled.
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


def section_box(title: str, help_key: str | None = None,
                header_extra: list | None = None) -> tuple[QGroupBox, QVBoxLayout]:
    """Return a styled QGroupBox and its inner layout, with optional ⓘ button.

    header_extra: optional list of QWidgets appended to the header row (before the stretch).
    """
    grp = QGroupBox()
    inner = QVBoxLayout(grp)
    inner.setContentsMargins(6, 4, 6, 6)
    inner.setSpacing(4)

    # Header row: title + help button + optional extras
    header = QWidget()
    hl = QHBoxLayout(header)
    hl.setContentsMargins(0, 0, 0, 0)
    hl.setSpacing(4)
    tlbl = QLabel(title)
    tlbl.setStyleSheet(f"color:{TEXT_HI}; font-size:{F_TITLE}; font-weight:bold; border:none;")
    _section_titles.append(tlbl)
    hl.addWidget(tlbl)
    if help_key and help_key in HELP:
        hbtn = HelpButton(HELP[help_key])
        _section_help_buttons.append(hbtn)
        hl.addWidget(hbtn)
    if header_extra:
        for w in header_extra:
            hl.addWidget(w)
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


def _arrow_btns(spinbox: QAbstractSpinBox) -> "QWidget":
    """Return a stacked [▲/▼] widget wired to spinbox; hides spinbox's native buttons.

    All buttons are registered in the module-level _arrow_btns_list so
    _switch_theme() can restyle them in a single pass.
    """
    spinbox.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    w = QWidget()
    vl = QVBoxLayout(w)
    vl.setContentsMargins(0, 0, 0, 0)
    vl.setSpacing(1)
    w.setFixedWidth(20)
    _sty = (f"font-size:9pt; padding:0px; color:{DARK_BG}; "
            f"background:{TEXT_HI}; border:1px solid {DARK_BORDER};")
    for sym, fn in (("▲", spinbox.stepUp), ("▼", spinbox.stepDown)):
        btn = QPushButton(sym)
        btn.setFixedHeight(13)
        btn.setFixedWidth(20)
        btn.setStyleSheet(_sty)
        btn.clicked.connect(fn)
        vl.addWidget(btn)
        _arrow_btns_list.append(btn)
    return w


# ── Config ─────────────────────────────────────────────────────────────────────
CONFIG_FILE = Path(__file__).with_name("spectro_config.json")

DEFAULTS: dict = {
    "watch_folder":         "",
    "file_filter":          "",
    "rotation_angle":       0.0,
    "target_y_start":       1000,
    "target_y_end":         1160,
    "bg_above_y_start":     880,
    "bg_above_y_end":       980,
    "bg_below_y_start":     1180,
    "bg_below_y_end":       1280,
    "saturation_threshold": 0.70,
    "target_fill":          0.80,
    "stretch_value":        3,
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
    "envelope_sigma":            1.0,
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

    def __init__(self, folder: str, interval_ms: int = 2000, filter_pattern: str = ""):
        super().__init__()
        self.folder = folder
        self.interval_ms = interval_ms
        self.filter_pattern = filter_pattern
        self._running = True
        self._known: set[str] = set()
        self._latest: str | None = None
        self._scan_existing()

    def _glob(self) -> list[Path]:
        p = Path(self.folder)
        seen: set[str] = set()
        files: list[Path] = []
        if p.exists():
            for pat in ("*.fits", "*.fit", "*.FITS", "*.FIT"):
                for f in p.glob(pat):
                    key = str(f.resolve()).lower()
                    if key not in seen:
                        seen.add(key)
                        files.append(f)
        if self.filter_pattern:
            files = [f for f in files if fnmatch.fnmatch(f.name, self.filter_pattern)]
        return files

    def _scan_existing(self):
        files = self._glob()
        self._known = {str(f) for f in files}
        if files:
            self._latest = str(max(files, key=lambda f: f.stat().st_mtime))

    def apply_filter(self, pattern: str):
        """Update the filter and re-scan so count/latest reflect the new pattern."""
        self.filter_pattern = pattern
        self._scan_existing()

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

    def total_count(self) -> int:
        """Number of FITS files in the folder ignoring any filename filter."""
        p = Path(self.folder)
        seen: set[str] = set()
        if p.exists():
            for pat in ("*.fits", "*.fit", "*.FITS", "*.FIT"):
                for f in p.glob(pat):
                    seen.add(str(f.resolve()).lower())
        return len(seen)


# ── Math helpers ───────────────────────────────────────────────────────────────
def rotate_image(data: np.ndarray, angle_deg: float) -> np.ndarray:
    if abs(angle_deg) < 1e-4:
        return data
    return rotate(data, angle_deg,
                  reshape=False, order=3, mode='reflect', prefilter=True).astype(np.float32)


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


# ── Wavelength calibration functions ─────────────────────────────────────────

def detect_slant(data: np.ndarray, y_lo: int, y_hi: int) -> float:
    """Measure spectral trace slant in degrees from a 2D lamp image."""
    strip = data[y_lo:y_hi, :].astype(np.float64)
    n_rows, n_cols = strip.shape
    if n_rows < 3 or n_cols < 50:
        return 0.0
    col_sum = strip.mean(axis=0)
    max_val = col_sum.max()
    if max_val <= 0:
        return 0.0
    peaks, props = find_peaks(col_sum, prominence=0.1 * max_val, distance=50)
    if len(peaks) < 3:
        return 0.0
    prom = props['prominences']
    order = np.argsort(prom)[::-1]
    peaks = peaks[order[:8]]
    y_coords = np.arange(n_rows, dtype=float)

    def _gaussian(y, amp, mu, sigma):
        return amp * np.exp(-(y - mu) ** 2 / (2 * sigma ** 2))

    centroid_ys, peak_cols = [], []
    for px_c in peaks:
        col_data = strip[:, px_c]
        try:
            p0 = [col_data.max(), n_rows / 2.0, 3.0]
            popt, _ = curve_fit(_gaussian, y_coords, col_data, p0=p0, maxfev=500)
            centroid_ys.append(popt[1])
            peak_cols.append(float(px_c))
        except Exception:
            continue
    if len(peak_cols) < 2:
        return 0.0
    slope, _ = np.polyfit(peak_cols, centroid_ys, 1)
    return float(np.clip(np.degrees(np.arctan(slope)), -5.0, 5.0))


def apply_slant_correction(data: np.ndarray, slant_deg: float) -> np.ndarray:
    # TODO: expose slant_deg via MainWindow so Spectrum tab can optionally
    # apply the same correction to science frames.
    return rotate(data.astype(np.float32), -slant_deg,
                  reshape=False, order=1, mode='nearest').astype(np.float32)


def extract_cal_spectrum(data: np.ndarray, y_lo: int, y_hi: int,
                         slant_deg: float = 0.0) -> np.ndarray:
    """Column-sum the calibration image within the target Y-region."""
    if abs(slant_deg) > 0.05:
        corrected = apply_slant_correction(data, slant_deg).astype(float)
    else:
        corrected = data.astype(float)
    strip = corrected[y_lo:y_hi + 1, :]
    return strip.sum(axis=0).astype(float)


def detect_emission_peaks(spectrum: np.ndarray) -> np.ndarray:
    """Find candidate emission-line pixel positions in a lamp spectrum."""
    from scipy.ndimage import uniform_filter1d
    sm = uniform_filter1d(spectrum.astype(float), size=3)
    if sm.max() <= 0:
        return np.array([], dtype=int)
    peaks, _ = find_peaks(sm, prominence=0.03 * sm.max(), width=1, distance=8)
    if len(peaks) < 2:
        return np.array([], dtype=int)
    return np.sort(peaks)


def _fit_best_order(px_arr: np.ndarray, wav_arr: np.ndarray) -> np.ndarray:
    """Select optimal polynomial order by BIC and return fitted coefficients."""
    n = len(px_arr)
    best_coef, best_bic = None, np.inf
    for order in [2, 3, 4]:
        if n < order + 2:
            continue
        if order > 2 and int(np.sum(wav_arr < 5500)) < 2:
            continue
        c = np.polyfit(px_arr, wav_arr, order)
        resid = wav_arr - np.polyval(c, px_arr)
        rss = float(np.sum(resid ** 2))
        k = order + 1
        bic = n * np.log(rss / n + 1e-12) + k * np.log(n)
        if bic < best_bic - 2.0:
            best_bic = bic
            best_coef = c
    if best_coef is None:
        best_coef = np.polyfit(px_arr, wav_arr, min(2, n - 1))
    return best_coef


def auto_solve_lamp(spectrum: np.ndarray, lamp_key: str):
    """Fully automatic lamp line matching. Returns result dict or None."""
    peaks = detect_emission_peaks(spectrum)
    if len(peaks) < 3:
        return None
    n_cols = len(spectrum)
    known_waves = [w for (_, w) in LAMP_LINES[lamp_key]["lines"]]

    # Grid search for linear seed
    lambda_starts = np.arange(3300, 4500, 10)
    dispersions   = np.arange(0.90, 1.81, 0.02)
    best_score, best_seed = 0, (3600.0, 1.1)
    tolerance_grid = 15
    for lam0 in lambda_starts:
        for d in dispersions:
            score = sum(
                1 for w in known_waves
                if 0 <= (w - lam0) / d <= n_cols
                and np.any(np.abs(peaks - (w - lam0) / d) <= tolerance_grid)
            )
            if score > best_score:
                best_score = score
                best_seed = (float(lam0), float(d))
    if best_score < 3:
        return None

    def _neg_score(params):
        lam0, d = params
        if d <= 0.1:
            return 0.0
        return -float(sum(
            1 for w in known_waves
            if 0 <= (w - lam0) / d <= n_cols
            and np.any(np.abs(peaks - (w - lam0) / d) <= 12)
        ))

    res = minimize(_neg_score, best_seed, method='Nelder-Mead',
                   options={'xatol': 1.0, 'fatol': 0.5, 'maxiter': 500})
    lam0, d = res.x
    if d <= 0.1:
        lam0, d = best_seed

    # Iterative match + polynomial refinement
    coef = np.array([d, lam0])
    matched_pairs = []
    for tol in [25, 12, 6]:
        new_pairs = []
        all_px = np.arange(n_cols)
        all_w  = np.polyval(coef, all_px)
        for (ion, wave) in LAMP_LINES[lamp_key]["lines"]:
            px_pred = float(all_px[np.argmin(np.abs(all_w - wave))])
            if not (0 <= px_pred <= n_cols - 1):
                continue
            near = peaks[np.abs(peaks - px_pred) <= tol]
            if len(near) == 0:
                continue
            best_peak = near[int(np.argmin(np.abs(near - px_pred)))]
            new_pairs.append((float(best_peak), wave, ion))
        if len(new_pairs) < 2:
            break
        matched_pairs = new_pairs
        px_arr  = np.array([p[0] for p in matched_pairs])
        wav_arr = np.array([p[1] for p in matched_pairs])
        coef = _fit_best_order(px_arr, wav_arr)

    if len(matched_pairs) < 4:
        return {"n_matched": len(matched_pairs)}

    px_arr  = np.array([p[0] for p in matched_pairs])
    wav_arr = np.array([p[1] for p in matched_pairs])
    fitted  = np.polyval(coef, px_arr)
    resid   = wav_arr - fitted
    rms_global = float(np.sqrt(np.mean(resid ** 2)))
    blue_mask  = wav_arr < 5500
    red_mask   = ~blue_mask
    rms_blue = float(np.sqrt(np.mean(resid[blue_mask] ** 2))) if blue_mask.any() else float('nan')
    rms_red  = float(np.sqrt(np.mean(resid[red_mask]  ** 2))) if red_mask.any()  else float('nan')
    all_w = np.polyval(coef, np.arange(n_cols))
    frame_min, frame_max = all_w.min(), all_w.max()
    n_total = sum(1 for (_, w) in LAMP_LINES[lamp_key]["lines"]
                  if frame_min <= w <= frame_max)
    return {
        "coef":          coef,
        "poly_order":    len(coef) - 1,
        "rms_global":    rms_global,
        "rms_blue":      rms_blue,
        "rms_red":       rms_red,
        "n_matched":     len(matched_pairs),
        "n_total":       n_total,
        "lambda_min":    float(wav_arr.min()),
        "lambda_max":    float(wav_arr.max()),
        "matched_pairs": matched_pairs,
    }


def fit_gaussian_absorption(x: np.ndarray, y: np.ndarray):
    """Find centroid of absorption dip in a sub-range of the 1D spectrum."""
    if len(x) < 5:
        return None
    n10 = max(1, len(x) // 10)
    x_bl = np.concatenate([x[:n10], x[-n10:]])
    y_bl = np.concatenate([y[:n10], y[-n10:]])
    slope_bl, intercept_bl = np.polyfit(x_bl.astype(float), y_bl.astype(float), 1)
    y_sub = y.astype(float) - (slope_bl * x.astype(float) + intercept_bl)
    y_inv = -y_sub

    def _gaussian(xv, amp, mu, sigma):
        return amp * np.exp(-(xv - mu) ** 2 / (2 * sigma ** 2))

    try:
        p0 = [float(y_inv.max()), float(x[y_inv.argmax()]), (float(x[-1]) - float(x[0])) / 6]
        bounds = ([0.0, float(x[0]), 1.0],
                  [np.inf, float(x[-1]), (float(x[-1]) - float(x[0])) / 2 + 1])
        popt, _ = curve_fit(_gaussian, x.astype(float), y_inv, p0=p0,
                             bounds=bounds, maxfev=1000)
        return float(popt[1])
    except Exception:
        return float(x[int(y_inv.argmax())])


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
    fwhm_px:           float | None  = None
    fwhm_reliable:     bool          = True
    n_continuum:       int           = 0
    spatial_centroid:  float | None  = None
    profile_asymmetry: float | None  = None
    total_flux:        float | None  = None
    inclusion:     str           = "included"   # 'included' | 'excluded' | 'flagged'
    flag_reasons:  list          = field(default_factory=list)
    user_kept:     bool          = False        # flagged but user explicitly chose to keep

    @property
    def peak_fill(self) -> float:
        return self.peak_adu / self.sat_limit if self.sat_limit > 0 else 0.0


# ── Wavelength calibration dataclass ──────────────────────────────────────────
@dataclass
class WavelengthCalibration:
    """Polynomial wavelength calibration result.

    coef follows numpy.polyfit convention: highest-degree coefficient first.
    pixel_to_wave(px) = numpy.polyval(coef, px)
    """
    coef:        list
    poly_order:  int
    rms_global:  float
    rms_blue:    float
    rms_red:     float
    n_matched:   int
    n_total:     int
    lambda_min:  float
    lambda_max:  float
    slant_deg:   float
    lamp_type:   str
    source_file: str
    timestamp:   str

    def pixel_to_wave(self, px) -> np.ndarray:
        return np.polyval(self.coef, np.asarray(px, dtype=float))

    def wave_to_pixel_approx(self, wave: float) -> float:
        px = np.arange(3840, dtype=float)
        lam = self.pixel_to_wave(px)
        idx = int(np.argmin(np.abs(lam - wave)))
        return float(idx)

    def to_dict(self) -> dict:
        import dataclasses as _dc
        return _dc.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "WavelengthCalibration":
        return cls(**d)


# ── Session data ──────────────────────────────────────────────────────────────
class SessionData:
    """Accumulates per-frame metrics and session-level online statistics."""

    def __init__(self):
        self.records:     list[FrameRecord]        = []
        self._spectra:    dict[int, np.ndarray]    = {}
        self._cont_masks: dict[int, np.ndarray]    = {}
        self._n_cols:     int                      = 0
        self.welford:          WelfordStats | None  = None
        self.persistence:      np.ndarray | None   = None   # fraction [0,1] per column
        self._persistence_raw: np.ndarray | None   = None   # raw exceedance counts
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
                self._n_cols          = n
                self.welford          = WelfordStats(n)
                self.persistence      = np.zeros(n)
                self._persistence_raw = np.zeros(n)
                self.snr_history      = []
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
            self._persistence_raw += (spec > prev_mean + 2.0 * prev_std).astype(float)
            eligible = wf.n - 2   # frames that could have triggered (need prior mean+std)
            self.persistence = self._persistence_raw / eligible
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
        eligible = max(len(included) - 2, 1)   # frames that could have triggered
        self.welford          = wf
        self._persistence_raw = persist
        self.persistence      = persist / eligible
        self.snr_history      = snr_h

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

    def _baseline5(self, attr: str) -> float | None:
        vals = []
        for r in self.included:
            v = getattr(r, attr)
            if v is not None:
                vals.append(v)
                if len(vals) == 5:
                    break
        return float(np.mean(vals)) if len(vals) >= 5 else None

    @property
    def baseline_total_flux(self) -> float | None:
        return self._baseline5("total_flux")

    @property
    def baseline_centroid(self) -> float | None:
        return self._baseline5("spatial_centroid")

    @property
    def baseline_asymmetry(self) -> float | None:
        return self._baseline5("profile_asymmetry")

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
        self._full_xlim             = None   # full-view limits (updated each refresh)
        self._full_ylim             = None
        self._zoomed                = False  # True = user has zoomed; persists across file loads
        self._zoom_xlim             = None   # saved user zoom limits
        self._zoom_ylim             = None

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

        self._full_xlim = None
        self._full_ylim = None
        self._zoom_patch = None
        self._zoom_start = None

        if fits_data is None:
            self.ax.text(0.5, 0.5, "No image loaded", color=TEXT,
                         ha="center", va="center", transform=self.ax.transAxes, fontsize=14)
            self.draw_idle()
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
        self._full_xlim = self.ax.get_xlim()
        self._full_ylim = self.ax.get_ylim()
        if self._zoomed:
            if self._zoom_xlim is not None:
                self.ax.set_xlim(self._zoom_xlim)
            if self._zoom_ylim is not None:
                self.ax.set_ylim(self._zoom_ylim)
        self.draw_idle()

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

    def set_xrange(self, x_min: float, x_max: float):
        """Sync x-axis from spectrum canvas zoom (preserves y-axis zoom)."""
        self.ax.set_xlim(x_min, x_max)
        self._zoomed    = True
        self._zoom_xlim = (x_min, x_max)
        # _zoom_ylim left unchanged so y-zoom from image drag is preserved
        self.draw_idle()

    def reset_zoom(self):
        """Restore full image view and clear persisted zoom state."""
        self._zoomed    = False
        self._zoom_xlim = None
        self._zoom_ylim = None
        if self._full_xlim is not None:
            self.ax.set_xlim(self._full_xlim)
            self.ax.set_ylim(self._full_ylim)
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
                self._zoomed   = True
                self._zoom_xlim = self.ax.get_xlim()
                self._zoom_ylim = self.ax.get_ylim()
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
    zoom_x_changed = pyqtSignal(float, float)

    def __init__(self):
        self.fig = Figure(facecolor=DARK_BG)
        super().__init__(self.fig)
        self.ax     = self.fig.add_subplot(111)
        self.ax_snr = self.ax.twinx()
        self.ax.set_facecolor(DARK_BG)
        self.fig.subplots_adjust(left=0.09, right=0.86, top=0.97, bottom=0.11)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._full_xlim  = None
        self._full_ylim  = None
        self._zoom_mode  = False
        self._zoom_start = None   # (x, y) data coords on press
        self._zoom_patch = None   # Rectangle being drawn
        self._zoomed     = False  # True = user zoom active; persists across file loads
        self._zoom_xlim  = None
        self._zoom_ylim  = None
        self._peak_col_max: float | None = None

        self.mpl_connect("button_press_event",   self._on_press)
        self.mpl_connect("motion_notify_event",  self._on_motion)
        self.mpl_connect("button_release_event", self._on_release)

    def refresh(self, fits_data, cfg):
        self.fig.set_facecolor(DARK_BG)
        self.ax.cla(); self.ax_snr.cla()
        self._full_xlim  = None
        self._full_ylim  = None
        self._peak_col_max = None
        for ax in (self.ax, self.ax_snr):
            ax.set_facecolor(DARK_BG)
            ax.tick_params(colors=TEXT, labelsize=8)
            for sp in ax.spines.values(): sp.set_edgecolor(DARK_BORDER)
        if fits_data is None:
            self.ax.text(0.5, 0.5, "No data", color=TEXT, ha="center", va="center",
                         transform=self.ax.transAxes); self.draw_idle(); return None

        data       = fits_data["data"]
        full_range = fits_data["full_range"]
        LINEARITY_FRAC  = 0.80
        linearity_limit = LINEARITY_FRAC * full_range   # e.g. 52428 for 16-bit

        x, spec, bg, tsum, n = extract_spectrum(
            data,
            (cfg["target_y_start"],   cfg["target_y_end"]),
            (cfg["bg_above_y_start"], cfg["bg_above_y_end"]),
            (cfg["bg_below_y_start"], cfg["bg_below_y_end"]),
        )

        def _col_max_hp(region: np.ndarray) -> np.ndarray:
            """2nd-highest pixel per column (hot-pixel filtered); falls back to max if 1 row."""
            if region.shape[0] >= 2:
                return np.partition(region, -2, axis=0)[-2, :].astype(float)
            return region.max(axis=0).astype(float)

        # Target: hot-pixel-filtered max per column
        h = data.shape[0]
        _y0 = min(int(cfg["target_y_start"]), int(cfg["target_y_end"]))
        _y1 = max(int(cfg["target_y_start"]), int(cfg["target_y_end"])) + 1
        col_max = _col_max_hp(data[max(0, _y0):min(h, _y1), :])
        self._peak_col_max = float(col_max.max()) if len(col_max) else None

        lin_line = linearity_limit

        self.ax.plot(x, col_max, color="white", lw=0.7, label="Max ADU (hot-px filtered)", zorder=2)
        self.ax.plot(x, bg,      color=BG_C,    lw=0.7, label="Sky background (bg/px)",    zorder=2)
        self.ax.axhline(lin_line,   color=SAT_C,   lw=1.2, ls=":",  alpha=0.85,
                        label="Linearity limit (80%)", zorder=4)

        # Saturation column shading
        shade_mask = col_max > lin_line
        in_run = False
        for i, s in enumerate(shade_mask):
            if s and not in_run:  start = i; in_run = True
            elif not s and in_run:
                self.ax.axvspan(start - 0.5, i - 1.5, facecolor=SAT_C, alpha=0.18, zorder=3)
                in_run = False
        if in_run:
            self.ax.axvspan(start - 0.5, len(shade_mask) - 0.5,
                            facecolor=SAT_C, alpha=0.18, zorder=3)

        # Y axis: fixed 0–full_range
        self.ax.set_ylim(0, full_range * 1.02)
        self.ax.set_xlabel("X pixel  (∝ wavelength)", color=TEXT, fontsize=9)
        self.ax.set_ylabel("ADU (max per column)", color=TEXT, fontsize=9)
        self.ax.yaxis.set_major_formatter(FuncFormatter(_fmt_spec_y))

        # Hide unused right axis
        self.ax_snr.set_yticks([])
        self.ax_snr.spines["right"].set_visible(False)

        h1, l1 = self.ax.get_legend_handles_labels()
        self.ax.legend(h1, l1, loc="upper right", fontsize=8,
                       facecolor=DARK_PANEL, edgecolor=DARK_BORDER, labelcolor=TEXT)

        # Save full limits, then re-apply persisted zoom if active
        self._full_xlim = self.ax.get_xlim()
        self._full_ylim = self.ax.get_ylim()
        if self._zoomed:
            if self._zoom_xlim is not None:
                self.ax.set_xlim(self._zoom_xlim)
            if self._zoom_ylim is not None:
                self.ax.set_ylim(self._zoom_ylim)
        self.draw_idle()
        return x, spec, bg, n

    def set_xrange(self, x_min: float, x_max: float, spec_data=None):
        """Synchronise x-axis from an external zoom (image or session canvas)."""
        self.ax.set_xlim(x_min, x_max)
        self._zoomed    = True
        self._zoom_xlim = (x_min, x_max)
        self.draw_idle()

    def reset_xrange(self):
        """Restore full view and clear persisted zoom state."""
        self._zoomed    = False
        self._zoom_xlim = None
        self._zoom_ylim = None
        if self._full_xlim is not None:
            self.ax.set_xlim(self._full_xlim)
        if self._full_ylim is not None:
            self.ax.set_ylim(self._full_ylim)
        self.draw_idle()

    def reset_zoom(self):
        self.reset_xrange()

    def zoom_to_data_range(self):
        """Zoom Y so the target peak sits at 80% of the visible scale."""
        if self._peak_col_max is None or self._peak_col_max <= 0:
            return
        y_top = self._peak_col_max / 0.80
        self.ax.set_ylim(0, y_top)
        self._zoomed    = True
        self._zoom_ylim = (0, y_top)
        self.draw_idle()

    def set_zoom_mode(self, enabled: bool):
        self._zoom_mode = enabled
        cursor = Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor
        self.setCursor(QCursor(cursor))

    def _to_ax_coords(self, event):
        """Convert event screen position to self.ax data coordinates.
        Needed because ax_snr (twinx) captures events and reports ydata
        in its own coordinate space, not ax's."""
        try:
            x, y = self.ax.transData.inverted().transform((event.x, event.y))
            return float(x), float(y)
        except Exception:
            return None, None

    def _on_press(self, event):
        if not self._zoom_mode or event.inaxes not in (self.ax, self.ax_snr) or event.button != 1:
            return
        x, y = self._to_ax_coords(event)
        if x is not None:
            self._zoom_start = (x, y)
            self._zoom_patch = Rectangle(
                (x, y), 0, 0,
                linewidth=1.5, edgecolor=ACCENT, facecolor=ACCENT,
                alpha=0.12, zorder=10, linestyle="--"
            )
            self.ax.add_patch(self._zoom_patch)
            self.draw_idle()

    def _on_motion(self, event):
        if not self._zoom_mode or self._zoom_start is None or self._zoom_patch is None:
            return
        if event.inaxes not in (self.ax, self.ax_snr):
            return
        x, y = self._to_ax_coords(event)
        if x is not None:
            x0, y0 = self._zoom_start
            self._zoom_patch.set_bounds(
                min(x0, x), min(y0, y),
                abs(x - x0), abs(y - y0)
            )
            self.draw_idle()

    def _on_release(self, event):
        if not self._zoom_mode or self._zoom_start is None:
            return
        x0, y0 = self._zoom_start
        self._zoom_start = None
        if self._zoom_patch is not None:
            self._zoom_patch.remove()
            self._zoom_patch = None
        x, y = self._to_ax_coords(event)
        if x is not None and abs(x - x0) > 5 and abs(y - y0) > 5:
            xl = sorted([x0, x])
            yl = sorted([y0, y])
            self.ax.set_xlim(xl[0], xl[1])
            self.ax.set_ylim(yl[0], yl[1])
            self._zoomed    = True
            self._zoom_xlim = tuple(self.ax.get_xlim())
            self._zoom_ylim = tuple(self.ax.get_ylim())
            self.draw_idle()
            self.zoom_x_changed.emit(xl[0], xl[1])
        else:
            self.draw_idle()


# ── Advisory panel ─────────────────────────────────────────────────────────────
class AdvisoryPanel(QWidget):
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        # ── Exposure Advisory ──
        self.btn_gain = QPushButton("Gain Advice: OFF")
        self.btn_gain.setCheckable(True)
        self.btn_gain.setFixedWidth(175)
        exp_grp, exp_lay = section_box("Exposure Advisory", "advisory",
                                       header_extra=[self.btn_gain])
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
        sat_limit  = 0.80 * full_range   # linearity limit: 80% of full ADU range

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

        bg_e_px = float(np.mean(np.maximum(bg_per_row, 0.0))) * G
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
        ab0 = _arrow_btns(self.y0)
        ab1 = _arrow_btns(self.y1)
        for w in (self._dot, self._band_lbl, QLabel("Y:"), self.y0, ab0,
                  self._arr, self.y1, ab1):
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
class SessionMetricsCanvas(FigureCanvas):
    def __init__(self):
        self.fig = Figure(facecolor=DARK_BG)
        super().__init__(self.fig)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor(DARK_BG)
        self.fig.subplots_adjust(left=0.14, right=0.97, top=0.92, bottom=0.22)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def refresh(self, session: SessionData,
                show_flux: bool, show_centroid: bool,
                show_asymmetry: bool, show_flux_rms: bool, show_fwhm: bool,
                warn_pct: float, alarm_pct: float, rms_window: int):
        self.fig.set_facecolor(DARK_BG)
        self.ax.cla()
        self.ax.set_facecolor(DARK_BG)
        for sp in self.ax.spines.values(): sp.set_edgecolor(DARK_BORDER)
        self.ax.tick_params(colors=TEXT, labelsize=8)
        self.ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        self.ax.set_xlabel("Included frame #", color=TEXT, fontsize=9)
        self.ax.set_ylabel("% from baseline", color=TEXT, fontsize=9)
        self.ax.set_title("Slit Quality Metrics", color=TEXT_HI, fontsize=9, pad=3)

        included = list(session.included)
        any_metric = show_flux or show_centroid or show_asymmetry or show_flux_rms or show_fwhm
        if not included or not any_metric:
            self.ax.text(0.5, 0.5, "No data yet", color=TEXT_DIM,
                         ha="center", va="center", transform=self.ax.transAxes, fontsize=10)
            self.draw_idle()
            return

        xs = list(range(1, len(included) + 1))

        def _pct_series(attr: str, baseline: float | None):
            if baseline is None or abs(baseline) < 1e-9:
                return [], []
            vx, vy = [], []
            for i, r in enumerate(included):
                v = getattr(r, attr)
                if v is not None:
                    vx.append(xs[i])
                    vy.append((v - baseline) / abs(baseline) * 100.0)
            return vx, vy

        any_plotted = False

        # ── Integrated Flux ────────────────────────────────────────────────
        if show_flux:
            bl = session.baseline_total_flux
            vx, vy = _pct_series("total_flux", bl)
            if vx:
                self.ax.plot(vx, vy, color=ACCENT, lw=0.8, zorder=2)
                self.ax.scatter(vx, vy, color=ACCENT, s=22, zorder=3,
                                label=f"Flux ({vy[-1]:+.1f}%)")
                any_plotted = True

        # ── Spatial Centroid Y ─────────────────────────────────────────────
        if show_centroid:
            bl = session.baseline_centroid
            vx, vy = _pct_series("spatial_centroid", bl)
            if vx:
                self.ax.plot(vx, vy, color=OK_COL, lw=0.8, zorder=2)
                self.ax.scatter(vx, vy, color=OK_COL, s=22, zorder=3,
                                label=f"Centroid ({vy[-1]:+.1f}%)")
                any_plotted = True

        # ── Profile Asymmetry ──────────────────────────────────────────────
        if show_asymmetry:
            vx, vy = [], []
            for i, r in enumerate(included):
                if r.profile_asymmetry is not None:
                    vx.append(xs[i])
                    vy.append(r.profile_asymmetry * 100.0)   # direct %, not vs baseline
            if vx:
                self.ax.plot(vx, vy, color=TEXT_HI, lw=0.8, zorder=2)
                self.ax.scatter(vx, vy, color=TEXT_HI, s=22, zorder=3,
                                label=f"Asymmetry ({vy[-1]:+.1f}%)")
                any_plotted = True

        # ── Flux RMS (rolling std) ─────────────────────────────────────────
        if show_flux_rms:
            all_fx = [(i, r.total_flux) for i, r in enumerate(included)
                      if r.total_flux is not None]
            if len(all_fx) >= rms_window:
                mean_f = abs(np.mean([f for _, f in all_fx])) or 1.0
                rms_x, rms_y = [], []
                for j in range(rms_window - 1, len(all_fx)):
                    win = [f for _, f in all_fx[j - rms_window + 1: j + 1]]
                    rms_x.append(all_fx[j][0] + 1)
                    rms_y.append(float(np.std(win)) / mean_f * 100.0)
                if rms_x:
                    self.ax.plot(rms_x, rms_y, color=WARN, lw=0.8, zorder=2)
                    self.ax.scatter(rms_x, rms_y, color=WARN, s=22, zorder=3,
                                    label=f"Flux RMS ({rms_y[-1]:.1f}%)")
                    any_plotted = True

        # ── FWHM (optional) ───────────────────────────────────────────────
        if show_fwhm:
            bl = session.baseline_fwhm
            if bl is not None and abs(bl) > 1e-9:
                vx, vy, vc = [], [], []
                for i, r in enumerate(included):
                    if r.fwhm_px is None:
                        continue
                    pct = (r.fwhm_px - bl) / abs(bl) * 100.0
                    vx.append(xs[i]); vy.append(pct)
                    if not r.fwhm_reliable:       vc.append(TEXT_DIM)
                    elif pct > alarm_pct:          vc.append(WARN)
                    elif pct > warn_pct:           vc.append(ACCENT)
                    else:                          vc.append(TEXT_DIM)
                if vx:
                    self.ax.plot(vx, vy, color=TEXT_DIM, lw=0.8, zorder=2)
                    for xi, yi, ci in zip(vx, vy, vc):
                        self.ax.scatter([xi], [yi], color=ci, s=22, zorder=3)
                    self.ax.axhline(warn_pct,  color=ACCENT, lw=0.5, ls=":", alpha=0.35)
                    self.ax.axhline(alarm_pct, color=WARN,   lw=0.5, ls=":", alpha=0.35)
                    any_plotted = True

        if not any_plotted:
            self.ax.text(0.5, 0.5, "Waiting for baseline (5 frames)…",
                         color=TEXT_DIM, ha="center", va="center",
                         transform=self.ax.transAxes, fontsize=9)

        # Reference lines
        self.ax.axhline(0,   color=TEXT,     lw=0.8, alpha=0.5, zorder=1)
        self.ax.axhline( 10, color=TEXT_DIM, lw=0.5, ls=":", alpha=0.25, zorder=1)
        self.ax.axhline(-10, color=TEXT_DIM, lw=0.5, ls=":", alpha=0.25, zorder=1)
        self.ax.axhline( 30, color=TEXT_DIM, lw=0.5, ls=":", alpha=0.25, zorder=1)
        self.ax.axhline(-30, color=TEXT_DIM, lw=0.5, ls=":", alpha=0.25, zorder=1)

        if any_plotted:
            self.ax.legend(loc="upper left", fontsize=7,
                           facecolor=DARK_PANEL, edgecolor=DARK_BORDER, labelcolor=TEXT)
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
        self.ax.xaxis.set_major_locator(MaxNLocator(integer=True))
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
        self._hdr = QPushButton("▶ Slit Quality  —  Flux: —  Cen: —  Asym: —  RMS: —")
        self._hdr.setCheckable(True)
        self._hdr.setStyleSheet(f"""
            QPushButton {{
                text-align:left; padding:4px 8px;
                background:{DARK_PANEL}; color:{TEXT};
                border:1px solid {DARK_BORDER}; border-radius:3px; font-size:11pt;
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

        # Toggle row
        tog_row = QWidget()
        tl = QHBoxLayout(tog_row)
        tl.setContentsMargins(0, 0, 0, 0); tl.setSpacing(10)
        self.cb_flux      = QCheckBox("Integrated Flux"); self.cb_flux.setChecked(True)
        self.cb_centroid  = QCheckBox("Spatial Centroid"); self.cb_centroid.setChecked(True)
        self.cb_asymmetry = QCheckBox("Profile Asymmetry"); self.cb_asymmetry.setChecked(True)
        self.cb_rms       = QCheckBox("Flux RMS"); self.cb_rms.setChecked(True)
        self.cb_fwhm      = QCheckBox("FWHM"); self.cb_fwhm.setChecked(False)
        for cb in (self.cb_flux, self.cb_centroid, self.cb_asymmetry, self.cb_rms, self.cb_fwhm):
            cb.toggled.connect(self._do_refresh)
            tl.addWidget(cb)
        tl.addStretch()
        bl.addWidget(tog_row)

        self._canvas = SessionMetricsCanvas()
        bl.addWidget(self._canvas)

        cfg_row = QWidget()
        cl = QHBoxLayout(cfg_row)
        cl.setContentsMargins(0, 0, 0, 0); cl.setSpacing(8)
        cl.addWidget(QLabel("Warn%:"))
        self.spin_warn = QSpinBox()
        self.spin_warn.setRange(5, 100); self.spin_warn.setValue(20)
        self.spin_warn.setFixedWidth(58)
        self.spin_warn.valueChanged.connect(self._do_refresh)
        cl.addWidget(self.spin_warn); cl.addWidget(_arrow_btns(self.spin_warn))
        cl.addWidget(QLabel("  Alarm%:"))
        self.spin_alarm = QSpinBox()
        self.spin_alarm.setRange(10, 200); self.spin_alarm.setValue(50)
        self.spin_alarm.setFixedWidth(58)
        self.spin_alarm.valueChanged.connect(self._do_refresh)
        cl.addWidget(self.spin_alarm); cl.addWidget(_arrow_btns(self.spin_alarm))
        cl.addWidget(QLabel("  RMS window:"))
        self.spin_rms_win = QSpinBox()
        self.spin_rms_win.setRange(3, 30); self.spin_rms_win.setValue(7)
        self.spin_rms_win.setFixedWidth(52)
        self.spin_rms_win.valueChanged.connect(self._do_refresh)
        cl.addWidget(self.spin_rms_win); cl.addWidget(_arrow_btns(self.spin_rms_win))
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
        fl.addWidget(self.spin_flat); fl.addWidget(_arrow_btns(self.spin_flat))
        fl.addWidget(QLabel("ADU/col"))
        fl.addStretch()
        bl.addWidget(flat_row)

        self._body.setVisible(False)
        outer.addWidget(self._body)

        self._summary = "Flux: —  Cen: —  Asym: —  RMS: —"
        self._last_session: SessionData | None = None

    def _toggle(self, checked: bool):
        self._expanded = checked
        self._update_header()
        self._body.setVisible(checked)

    def _update_header(self):
        arrow = "▼" if self._expanded else "▶"
        self._hdr.setText(f"{arrow} Slit Quality  —  {self._summary}")

    def _do_refresh(self):
        if self._last_session is not None:
            self.refresh(self._last_session)

    def _restyle(self):
        if _is_day_mode:
            self._hdr.setStyleSheet("")
            self._help_btn.setStyleSheet("")
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
        self._flat_lbl.setStyleSheet(f"color:{TEXT_DIM}; font-size:10pt; border:none;")

    def refresh(self, session: SessionData):
        self._last_session = session
        warn    = float(self.spin_warn.value())
        alarm   = float(self.spin_alarm.value())
        rms_win = self.spin_rms_win.value()
        self._canvas.refresh(
            session,
            show_flux      = self.cb_flux.isChecked(),
            show_centroid  = self.cb_centroid.isChecked(),
            show_asymmetry = self.cb_asymmetry.isChecked(),
            show_flux_rms  = self.cb_rms.isChecked(),
            show_fwhm      = self.cb_fwhm.isChecked(),
            warn_pct=warn, alarm_pct=alarm, rms_window=rms_win,
        )

        # Build summary text from latest included frame
        inc  = list(session.included)
        last = inc[-1] if inc else None

        def _f(v):
            return f"{v/1000:.0f}k" if v is not None else "—"
        def _c(v):
            return f"{v:.1f} px" if v is not None else "—"
        def _a(v):
            return f"{v*100:+.1f}%" if v is not None else "—"

        flux_str = _f(last.total_flux if last else None)
        cen_str  = _c(last.spatial_centroid if last else None)
        asym_str = _a(last.profile_asymmetry if last else None)

        # RMS: last value from rolling computation
        rms_str = "—"
        all_fx = [(i, r.total_flux) for i, r in enumerate(inc) if r.total_flux is not None]
        if len(all_fx) >= rms_win:
            mean_f = abs(np.mean([f for _, f in all_fx])) or 1.0
            win = [f for _, f in all_fx[-rms_win:]]
            rms_str = f"{float(np.std(win))/mean_f*100:.1f}%"

        self._summary = f"Flux: {flux_str}  Cen: {cen_str}  Asym: {asym_str}  RMS: {rms_str}"
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
        self.spin_sigma.setRange(1, 3); self.spin_sigma.setValue(1)
        self.spin_sigma.setFixedWidth(48)
        cl.addWidget(self.spin_sigma); cl.addWidget(_arrow_btns(self.spin_sigma))
        cl.addWidget(QLabel("σ   Persist:"))
        self.spin_persist = QDoubleSpinBox()
        self.spin_persist.setRange(0.50, 1.00); self.spin_persist.setSingleStep(0.05)
        self.spin_persist.setValue(0.70); self.spin_persist.setFixedWidth(62)
        cl.addWidget(self.spin_persist); cl.addWidget(_arrow_btns(self.spin_persist))
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
        cl.addWidget(self.spin_snr_tgt); cl.addWidget(_arrow_btns(self.spin_snr_tgt))
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
    file_selected       = pyqtSignal(str)

    _COL_BASE    = ["#", "File", "Peak ADU", "Cont SNR", "FWHM", "Status", "★", "Incl."]
    _COL_HEADERS = _COL_BASE          # reference kept for index lookups
    _COL_INCL    = 7                  # "Incl." column index
    _COL_NOM     = 6                  # "★" nominate column index

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
                border:1px solid {DARK_BORDER}; border-radius:3px; font-size:11pt;
            }}
            QPushButton:checked {{ color:{ACCENT}; }}
        """)
        self._hdr.toggled.connect(self._toggle)
        outer.addWidget(self._hdr)

        # ── auto-flag config row ──────────────────────────────────────────────
        self._cfg_widget = QWidget()
        cl = QHBoxLayout(self._cfg_widget)
        cl.setContentsMargins(4, 2, 4, 2); cl.setSpacing(8)
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
        self.btn_nominate = QPushButton("★ Nominate OK")
        self.btn_nominate.setFixedWidth(140)
        self.btn_nominate.setToolTip(
            "Step 1: auto-select all OK frames for export.\n"
            "Step 2: copy selected (★) files to a \\nominated sub-folder.\n"
            "You can manually toggle the ★ checkboxes between steps.")
        self.btn_nominate.clicked.connect(self._on_nominate_clicked)
        self._nominate_state = 0
        cl.addWidget(self.btn_nominate)
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
        self._tbl.setFixedHeight(200)
        self._tbl.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self._tbl.itemChanged.connect(self._on_item_changed)
        self._tbl.cellDoubleClicked.connect(self._on_cell_clicked)
        tl.addWidget(self._tbl)
        self._tbl_widget.setVisible(False)
        outer.addWidget(self._tbl_widget)

        self._session: SessionData | None = None
        self._updating = False
        self._nominated: set[str] = set()
        self._display_order: list[int] = []
        self._sort_state: dict[int, int] = {}  # col → 0=default,1=asc,2=desc

    # ─────────────────────────────────────────────────────────────────────────
    def _toggle(self, checked: bool):
        self._expanded = checked
        arrow = "▼" if checked else "▶"
        self._hdr.setText(arrow + self._hdr.text()[1:])
        self._cfg_widget.setVisible(checked)
        self._tbl_widget.setVisible(checked)

    # ── sort ─────────────────────────────────────────────────────────────────
    def _on_header_clicked(self, col: int):
        if self._session is None:
            return
        cur = self._sort_state.get(col, 0)
        nxt = (cur + 1) % 3
        self._sort_state = {col: nxt}
        n = len(self._session.records)
        self._display_order = list(range(n))
        if nxt != 0:
            self._apply_sort(col, nxt)
        # Update header labels with sort indicator
        for i, h in enumerate(self._COL_BASE):
            self._tbl.setHorizontalHeaderItem(i, QTableWidgetItem(h))
        if nxt == 1:
            ind = " ▲"
        elif nxt == 2:
            ind = " ▼"
        else:
            ind = ""
        self._tbl.setHorizontalHeaderItem(
            col, QTableWidgetItem(self._COL_BASE[col] + ind))
        self.refresh(self._session)

    def _apply_sort(self, col: int, direction: int):
        recs = self._session.records
        rev  = (direction == 2)

        def _none_last(val, fallback=0.0):
            return (val is None, val if val is not None else fallback)

        if   col == 0: key = lambda i: recs[i].frame_number
        elif col == 1: key = lambda i: recs[i].filename.lower()
        elif col == 2: key = lambda i: recs[i].peak_adu
        elif col == 3: key = lambda i: _none_last(recs[i].continuum_snr)
        elif col == 4: key = lambda i: _none_last(recs[i].fwhm_px)
        elif col == 5:
            _ord = {"included": 0, "flagged": 1, "excluded": 2}
            key  = lambda i: _ord.get(recs[i].inclusion, 3)
        else:
            key = lambda i: i
        self._display_order.sort(key=key, reverse=rev)

    # ── nominate / export ─────────────────────────────────────────────────────
    def _on_nominate_clicked(self):
        if self._nominate_state == 0:
            # Auto-select all OK (fully included, not flagged) frames
            self._nominated.clear()
            if self._session:
                for rec in self._session.records:
                    if rec.inclusion == "included" and rec.filepath:
                        self._nominated.add(rec.filepath)
            self._nominate_state = 1
            self.btn_nominate.setText("Copy ► \\nominated")
            if self._session:
                self.refresh(self._session)
        else:
            self._do_copy_nominated()
            self._nominate_state = 0
            self.btn_nominate.setText("★ Nominate OK")
            self._nominated.clear()
            if self._session:
                self.refresh(self._session)

    def _do_copy_nominated(self):
        paths = [Path(fp) for fp in self._nominated if fp]
        if not paths:
            return
        target_dir = paths[0].parent / "nominated"
        target_dir.mkdir(exist_ok=True)
        for p in paths:
            if p.exists():
                shutil.copy2(p, target_dir / p.name)

    # ── table item callbacks ──────────────────────────────────────────────────
    def _rec_for_row(self, row: int):
        if self._session is None:
            return None
        idx = self._display_order[row] if row < len(self._display_order) else row
        if idx >= len(self._session.records):
            return None
        return self._session.records[idx]

    def _on_item_changed(self, item: QTableWidgetItem):
        if self._updating or self._session is None:
            return
        col = item.column()
        rec = self._rec_for_row(item.row())
        if rec is None:
            return
        if col == self._COL_NOM:
            if item.checkState() == Qt.CheckState.Checked:
                if rec.filepath:
                    self._nominated.add(rec.filepath)
            else:
                self._nominated.discard(rec.filepath or "")
        elif col == self._COL_INCL:
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
        if col in (self._COL_NOM, self._COL_INCL) or self._updating:
            return
        rec = self._rec_for_row(row)
        if rec and rec.filepath:
            self.file_selected.emit(rec.filepath)

    # ── refresh ───────────────────────────────────────────────────────────────
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

        if len(self._display_order) != n_tot:
            self._display_order = list(range(n_tot))

        self._updating = True
        try:
            self._tbl.setRowCount(n_tot)
            for display_row, rec_idx in enumerate(self._display_order):
                rec = session.records[rec_idx]

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
                for ci, it in enumerate(cells):
                    it.setBackground(row_bg)
                    self._tbl.setItem(display_row, ci, it)

                # ★ Nominate checkbox (col 6)
                nom_it = QTableWidgetItem()
                nom_it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                nom_it.setCheckState(
                    Qt.CheckState.Checked
                    if rec.filepath and rec.filepath in self._nominated
                    else Qt.CheckState.Unchecked)
                nom_it.setBackground(row_bg)
                self._tbl.setItem(display_row, self._COL_NOM, nom_it)

                # Incl. checkbox (col 7)
                chk_it = QTableWidgetItem()
                chk_it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                chk_it.setCheckState(
                    Qt.CheckState.Checked if rec.inclusion != "excluded"
                    else Qt.CheckState.Unchecked)
                chk_it.setBackground(row_bg)
                self._tbl.setItem(display_row, self._COL_INCL, chk_it)

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

    def append_note(self, text: str):
        """Append a line of text (e.g., region settings) and save immediately."""
        if self._path is None:
            return
        self._edit.blockSignals(True)
        cur = self._edit.toPlainText().rstrip("\n")
        self._edit.setPlainText(cur + "\n" + text + "\n")
        self._edit.blockSignals(False)
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


# ── Calibration canvases ──────────────────────────────────────────────────────

class CalibrationImageCanvas(FigureCanvas):
    region_changed = pyqtSignal(int, int)

    def __init__(self, parent=None):
        self._fig = Figure(figsize=(5, 2.2), facecolor=DARK_BG)
        super().__init__(self._fig)
        self._ax = self._fig.add_axes([0, 0, 1, 1])
        self._data = None
        self._y_lo = 80
        self._y_hi = 160
        self._slant_deg = 0.0
        self._drag_line = None
        self._line_lo = None
        self._line_hi = None
        self.mpl_connect('button_press_event',   self._on_press)
        self.mpl_connect('motion_notify_event',  self._on_motion)
        self.mpl_connect('button_release_event', self._on_release)

    def load(self, data: np.ndarray):
        self._data = data.astype(np.float32)
        self.refresh()

    def set_region(self, y_lo: int, y_hi: int):
        self._y_lo = y_lo
        self._y_hi = y_hi
        if self._line_lo is not None:
            self._line_lo.set_ydata([y_lo, y_lo])
        if self._line_hi is not None:
            self._line_hi.set_ydata([y_hi, y_hi])
        self.draw_idle()

    def refresh(self):
        ax = self._ax
        ax.clear()
        ax.set_facecolor(DARK_BG)
        if self._data is None:
            self._fig.set_facecolor(DARK_BG)
            self.draw_idle()
            return
        flat = self._data.ravel()
        vlo = float(np.percentile(flat, 1))
        vhi = float(np.percentile(flat, 99))
        n_rows, n_cols = self._data.shape
        ax.imshow(self._data, aspect='auto', origin='upper',
                  vmin=vlo, vmax=vhi, cmap='gray', interpolation='nearest')
        self._line_lo, = ax.plot([0, n_cols - 1], [self._y_lo, self._y_lo],
                                  '--', color=TARGET_C, linewidth=1.2)
        self._line_hi, = ax.plot([0, n_cols - 1], [self._y_hi, self._y_hi],
                                  '--', color=TARGET_C, linewidth=1.2)
        if abs(self._slant_deg) > 0.05:
            slope = np.tan(np.radians(self._slant_deg))
            y_mid = (self._y_lo + self._y_hi) / 2.0
            y0 = y_mid - slope * n_cols / 2.0
            y1 = y_mid + slope * n_cols / 2.0
            ax.plot([0, n_cols - 1], [y0, y1], color=WARN, alpha=0.4, linewidth=1)
            ax.text(0.98, 0.05, f"slant {self._slant_deg:+.2f}°",
                    transform=ax.transAxes, ha='right', va='bottom',
                    fontsize=8, color=ACCENT)
        ax.set_xlim(0, n_cols - 1)
        ax.set_ylim(n_rows - 1, 0)
        ax.axis('off')
        self._fig.set_facecolor(DARK_BG)
        self.draw_idle()

    def _on_press(self, event):
        if event.inaxes != self._ax or event.ydata is None:
            return
        y = event.ydata
        if abs(y - self._y_lo) <= 5:
            self._drag_line = 'lo'
            self.setCursor(QCursor(Qt.CursorShape.SizeVerCursor))
        elif abs(y - self._y_hi) <= 5:
            self._drag_line = 'hi'
            self.setCursor(QCursor(Qt.CursorShape.SizeVerCursor))

    def _on_motion(self, event):
        if self._drag_line is None:
            if event.inaxes == self._ax and event.ydata is not None:
                y = event.ydata
                if abs(y - self._y_lo) <= 5 or abs(y - self._y_hi) <= 5:
                    self.setCursor(QCursor(Qt.CursorShape.SizeVerCursor))
                else:
                    self.unsetCursor()
            return
        if event.ydata is None:
            return
        yi = int(round(event.ydata))
        if self._drag_line == 'lo':
            self._y_lo = yi
            if self._line_lo is not None:
                self._line_lo.set_ydata([yi, yi])
        else:
            self._y_hi = yi
            if self._line_hi is not None:
                self._line_hi.set_ydata([yi, yi])
        self.draw_idle()

    def _on_release(self, event):
        if self._drag_line is not None:
            self._drag_line = None
            self.unsetCursor()
            self.region_changed.emit(self._y_lo, self._y_hi)


class CalibrationSpectrumCanvas(FigureCanvas):
    span_selected = pyqtSignal(float, float)

    def __init__(self, parent=None):
        fig = Figure(figsize=(5, 1.4), facecolor=DARK_BG)
        super().__init__(fig)
        self._fig = fig
        self._ax = fig.add_subplot(111)
        self._ax.set_facecolor(DARK_BG)
        fig.subplots_adjust(left=0.06, right=0.97, top=0.88, bottom=0.25)
        self._spectrum = None
        self._matched_pairs = []
        self._range_selector = None

    def refresh(self, spectrum: np.ndarray, matched_pairs=None):
        self._spectrum = spectrum
        self._matched_pairs = matched_pairs or []
        ax = self._ax
        ax.clear()
        ax.set_facecolor(DARK_BG)
        if spectrum is not None and len(spectrum) > 0:
            x = np.arange(len(spectrum))
            ax.plot(x, spectrum, color=SPEC_C, linewidth=0.8)
            smax = float(spectrum.max()) if spectrum.max() > 0 else 1.0
            for (px, wave, ion) in self._matched_pairs:
                ax.axvline(px, color=ACCENT, alpha=0.6, linewidth=0.8, linestyle='--')
                ax.text(px, -0.12 * smax, f"{ion}\n{wave:.0f}",
                        ha='center', va='top', fontsize=6, color=ACCENT,
                        clip_on=True)
        ax.set_xlabel("pixel", fontsize=7, color=TEXT)
        ax.tick_params(colors=TEXT_DIM, labelsize=6)
        for sp in ax.spines.values():
            sp.set_edgecolor(DARK_BORDER)
        self._fig.set_facecolor(DARK_BG)
        self.draw_idle()
        # Recreate span selector if it was active
        if self._range_selector is not None:
            self.enable_span_selector(True)

    def enable_span_selector(self, enabled: bool):
        if self._range_selector is not None:
            self._range_selector.set_visible(False)
            self._range_selector = None
        if enabled:
            self._range_selector = SpanSelector(
                self._ax, self._on_span, 'horizontal',
                props=dict(facecolor=ACCENT, alpha=0.2),
                useblit=False,
            )
        self.draw_idle()

    def _on_span(self, xmin: float, xmax: float):
        if xmax > xmin:
            self.span_selected.emit(float(xmin), float(xmax))


class CalibrationResidualsCanvas(FigureCanvas):
    def __init__(self, parent=None):
        fig = Figure(figsize=(5, 1.1), facecolor=DARK_BG)
        super().__init__(fig)
        self._fig = fig
        self._ax = fig.add_subplot(111)
        self._ax.set_facecolor(DARK_BG)
        fig.subplots_adjust(left=0.10, right=0.97, top=0.88, bottom=0.32)
        self._clear_axes()
        self.draw_idle()

    def _clear_axes(self):
        ax = self._ax
        ax.clear()
        ax.set_facecolor(DARK_BG)
        ax.axhline(0, color=TEXT_DIM, linewidth=0.5)
        ax.set_ylabel("Δ Å", fontsize=7, color=TEXT)
        ax.set_xlabel("wavelength (Å)", fontsize=7, color=TEXT)
        ax.tick_params(colors=TEXT_DIM, labelsize=6)
        for sp in ax.spines.values():
            sp.set_edgecolor(DARK_BORDER)
        self._fig.set_facecolor(DARK_BG)

    def refresh(self, matched_pairs: list, coef: np.ndarray):
        self._clear_axes()
        ax = self._ax
        if not matched_pairs:
            self.draw_idle()
            return
        residuals = [(float(np.polyval(coef, px)), wave - float(np.polyval(coef, px)), ion, wave)
                     for (px, wave, ion) in matched_pairs]
        max_resid = max(abs(r[1]) for r in residuals) if residuals else 0
        ylim = max(max_resid * 1.4, 1.0)
        for (fw, resid, ion, wave) in residuals:
            col = '#4466ff' if wave < 5500 else WARN
            ax.scatter([fw], [resid], s=30, color=col, zorder=3)
            ax.vlines(fw, 0, resid, colors=col, alpha=0.4, linewidth=1)
            va = 'bottom' if resid >= 0 else 'top'
            ax.text(fw, resid, f"{resid:+.2f}", fontsize=7, color=col,
                    ha='center', va=va)
        ax.set_ylim(-ylim, ylim)
        self.draw_idle()

    def clear(self):
        self._clear_axes()
        self.draw_idle()


class CoverageBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._lambda_min = WAVE_MIN_DEFAULT
        self._lambda_max = WAVE_MAX_DEFAULT
        self.setFixedHeight(24)
        self.setMinimumWidth(180)

    def set_range(self, lmin: float, lmax: float):
        self._lambda_min = lmin
        self._lambda_max = lmax
        self.update()

    def paintEvent(self, event):
        from PyQt6.QtGui import QPainter, QColor, QPen
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        w, h = self.width(), self.height()
        wave_range = WAVE_MAX_DEFAULT - WAVE_MIN_DEFAULT
        # Background track
        p.fillRect(0, 4, w, h - 8, QColor(DARK_PANEL))
        p.setPen(QPen(QColor(DARK_BORDER), 1))
        p.drawRect(0, 4, w - 1, h - 9)
        # Calibrated region
        x0 = int((self._lambda_min - WAVE_MIN_DEFAULT) / wave_range * w)
        x1 = int((self._lambda_max - WAVE_MIN_DEFAULT) / wave_range * w)
        x0 = max(0, min(x0, w))
        x1 = max(0, min(x1, w))
        if x1 > x0:
            p.fillRect(x0, 4, x1 - x0, h - 8, QColor(OK_COL))
        # Labels
        font = p.font()
        font.setPointSize(7)
        p.setFont(font)
        p.setPen(QColor(TEXT_DIM))
        p.drawText(2, h - 2, "3500")
        p.drawText(w - 28, h - 2, "8000")
        mid_x = (x0 + x1) // 2
        label = f"{self._lambda_min:.0f}–{self._lambda_max:.0f} Å"
        fm = p.fontMetrics()
        lw = fm.horizontalAdvance(label)
        p.setPen(QColor(DARK_BG))
        p.drawText(max(x0, mid_x - lw // 2), h - 4, label)
        p.end()


class CalibrationTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data      = None
        self._cal_path  = None
        self._spectrum  = None
        self._cal: WavelengthCalibration | None = None
        self._matched_pairs: list = []
        self._balmer_pairs:  list = []
        self._pending_px     = None
        self._last_slant     = 0.0
        self._build_ui()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        # ── LEFT COLUMN ──────────────────────────────────────────────────────
        left_widget = QWidget()
        left_widget.setFixedWidth(420)
        left_col = QVBoxLayout(left_widget)
        left_col.setContentsMargins(0, 0, 0, 0)
        left_col.setSpacing(4)

        # File header
        file_bar = QWidget()
        file_lay = QHBoxLayout(file_bar)
        file_lay.setContentsMargins(0, 0, 0, 0)
        self._load_btn = QPushButton("Load Cal Image")
        self._load_btn.clicked.connect(self._on_load_file)
        self._file_lbl = QLabel("No file loaded")
        self._file_lbl.setStyleSheet(f"color:{TEXT_DIM}; font-size:{F_SM};")
        self._file_lbl.setSizePolicy(QSizePolicy.Policy.Expanding,
                                     QSizePolicy.Policy.Preferred)
        file_lay.addWidget(self._load_btn)
        file_lay.addWidget(self._file_lbl)
        left_col.addWidget(file_bar)

        # Calibration image canvas
        self._image_canvas = CalibrationImageCanvas()
        self._image_canvas.setFixedHeight(180)
        self._image_canvas.region_changed.connect(self._on_canvas_region_changed)
        left_col.addWidget(self._image_canvas)

        # Region bar
        region_bar = QWidget()
        rb_lay = QHBoxLayout(region_bar)
        rb_lay.setContentsMargins(0, 0, 0, 0)
        rb_lay.setSpacing(6)
        y_lbl = QLabel("Y:")
        y_lbl.setStyleSheet(f"color:{TEXT}; font-size:{F_SM}; border:none;")
        self._ylo_spin = QSpinBox()
        self._ylo_spin.setRange(0, 9999)
        self._ylo_spin.setFixedWidth(65)
        self._ylo_spin.valueChanged.connect(self._on_region_spin_changed)
        arr_lbl = QLabel("→")
        arr_lbl.setStyleSheet(f"color:{TEXT_DIM}; font-size:{F_SM}; border:none;")
        self._yhi_spin = QSpinBox()
        self._yhi_spin.setRange(0, 9999)
        self._yhi_spin.setFixedWidth(65)
        self._yhi_spin.valueChanged.connect(self._on_region_spin_changed)
        inh_lbl = QLabel("inherited from TARGET")
        inh_lbl.setStyleSheet(f"color:{TEXT_DIM}; font-size:{F_SM}; border:none;")
        no_bg_lbl = QLabel("(no BG subtraction)")
        no_bg_lbl.setStyleSheet(f"color:{TEXT_DIM}; font-size:9pt; border:none;")
        for w in (y_lbl, self._ylo_spin, arr_lbl, self._yhi_spin, inh_lbl):
            rb_lay.addWidget(w)
        rb_lay.addStretch()
        rb_lay.addWidget(no_bg_lbl)
        left_col.addWidget(region_bar)

        # Spectrum canvas
        self._spec_canvas = CalibrationSpectrumCanvas()
        self._spec_canvas.setFixedHeight(120)
        self._spec_canvas.span_selected.connect(self._on_span_selected)
        left_col.addWidget(self._spec_canvas)

        # Residuals canvas
        self._res_canvas = CalibrationResidualsCanvas()
        self._res_canvas.setFixedHeight(95)
        left_col.addWidget(self._res_canvas)

        left_col.addStretch()
        root.addWidget(left_widget)

        # ── RIGHT COLUMN ─────────────────────────────────────────────────────
        right_widget = QWidget()
        right_col = QVBoxLayout(right_widget)
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(6)

        # Mode selector
        mode_bar = QWidget()
        mode_lay = QHBoxLayout(mode_bar)
        mode_lay.setContentsMargins(0, 0, 0, 0)
        mode_lbl = QLabel("Mode:")
        mode_lbl.setStyleSheet(f"color:{TEXT_DIM}; font-size:10pt; border:none;")
        self._mode_lamp_btn   = QPushButton("Lamp")
        self._mode_lamp_btn.setCheckable(True)
        self._mode_lamp_btn.setChecked(True)
        self._mode_balmer_btn = QPushButton("Balmer / stellar")
        self._mode_balmer_btn.setCheckable(True)
        self._mode_group = QButtonGroup()
        self._mode_group.addButton(self._mode_lamp_btn,   0)
        self._mode_group.addButton(self._mode_balmer_btn, 1)
        self._mode_group.idClicked.connect(self._on_mode_changed)
        for w in (mode_lbl, self._mode_lamp_btn, self._mode_balmer_btn):
            mode_lay.addWidget(w)
        mode_lay.addStretch()
        right_col.addWidget(mode_bar)

        # Lamp panel
        self._lamp_panel = QWidget()
        lp_lay = QVBoxLayout(self._lamp_panel)
        lp_lay.setContentsMargins(0, 0, 0, 0)
        lp_lay.setSpacing(4)
        lamp_row = QWidget()
        lr_lay = QHBoxLayout(lamp_row)
        lr_lay.setContentsMargins(0, 0, 0, 0)
        lamp_lbl = QLabel("Lamp:")
        lamp_lbl.setStyleSheet(f"color:{TEXT}; border:none;")
        self._lamp_combo = QComboBox()
        for key in LAMP_LINES:
            self._lamp_combo.addItem(LAMP_LINES[key]["label"], userData=key)
        for i in range(self._lamp_combo.count()):
            if self._lamp_combo.itemData(i) == "ArH":
                self._lamp_combo.setCurrentIndex(i)
                break
        self._lamp_combo.currentIndexChanged.connect(lambda _: self._on_lamp_changed())
        self._solve_btn = QPushButton("Solve")
        self._solve_btn.clicked.connect(self._on_solve)
        self._solve_btn.setEnabled(False)
        for w in (lamp_lbl, self._lamp_combo, self._solve_btn):
            lr_lay.addWidget(w)
        self._lamp_combo.setSizePolicy(QSizePolicy.Policy.Expanding,
                                       QSizePolicy.Policy.Preferred)
        lp_lay.addWidget(lamp_row)
        self._warn_label = QLabel("")
        self._warn_label.setStyleSheet(f"color:{WARN}; font-size:{F_SM}; border:none;")
        self._warn_label.setWordWrap(True)
        lp_lay.addWidget(self._warn_label)
        right_col.addWidget(self._lamp_panel)

        # Balmer panel
        self._balmer_panel = QWidget()
        bp_lay = QVBoxLayout(self._balmer_panel)
        bp_lay.setContentsMargins(0, 0, 0, 0)
        bp_lay.setSpacing(4)
        instr_lbl = QLabel("Drag a range over each absorption dip, then assign it.")
        instr_lbl.setStyleSheet(f"color:{TEXT_DIM}; font-size:{F_SM}; border:none;")
        instr_lbl.setWordWrap(True)
        bp_lay.addWidget(instr_lbl)
        self._balmer_list = QListWidget()
        self._balmer_list.setMaximumHeight(90)
        self._balmer_list.setStyleSheet(
            f"QListWidget {{ background:{DARK_PANEL}; color:{TEXT}; "
            f"border:1px solid {DARK_BORDER}; font-size:{F_SM}; }}")
        bp_lay.addWidget(self._balmer_list)
        assign_row = QWidget()
        ar_lay = QHBoxLayout(assign_row)
        ar_lay.setContentsMargins(0, 0, 0, 0)
        self._line_combo = QComboBox()
        for (name, wave) in STELLAR_LINES:
            self._line_combo.addItem(f"{name}  {wave:.2f} Å")
        self._assign_btn = QPushButton("Assign")
        self._assign_btn.clicked.connect(self._on_assign_balmer)
        self._clear_balmer_btn = QPushButton("Clear")
        self._clear_balmer_btn.clicked.connect(self._on_clear_balmer)
        for w in (self._line_combo, self._assign_btn, self._clear_balmer_btn):
            ar_lay.addWidget(w)
        self._line_combo.setSizePolicy(QSizePolicy.Policy.Expanding,
                                       QSizePolicy.Policy.Preferred)
        bp_lay.addWidget(assign_row)
        right_col.addWidget(self._balmer_panel)
        self._balmer_panel.setVisible(False)

        # Slant section
        slant_frame = QFrame()
        slant_lay = QHBoxLayout(slant_frame)
        slant_lay.setContentsMargins(4, 2, 4, 2)
        slant_lbl = QLabel("Slant:")
        slant_lbl.setStyleSheet(f"color:{TEXT_DIM}; font-size:10pt; border:none;")
        self._slant_val_label = QLabel("—")
        self._slant_val_label.setStyleSheet(f"color:{ACCENT}; border:none;")
        self._slant_apply_chk = QCheckBox("Apply correction")
        for w in (slant_lbl, self._slant_val_label):
            slant_lay.addWidget(w)
        slant_lay.addStretch()
        slant_lay.addWidget(self._slant_apply_chk)
        right_col.addWidget(slant_frame)

        # Result section
        self._result_section = QWidget()
        rs_lay = QVBoxLayout(self._result_section)
        rs_lay.setContentsMargins(0, 0, 0, 0)
        rs_lay.setSpacing(4)
        cards_widget = QWidget()
        cards_grid = QGridLayout(cards_widget)
        cards_grid.setContentsMargins(0, 0, 0, 0)
        cards_grid.setSpacing(4)
        self._card_rms_global = self._make_metric_card("RMS global",       "—")
        self._card_matched    = self._make_metric_card("Lines matched",     "—")
        self._card_rms_blue   = self._make_metric_card("RMS blue (<5500)", "—")
        self._card_rms_red    = self._make_metric_card("RMS red (≥5500)",  "—")
        cards_grid.addWidget(self._card_rms_global[0], 0, 0)
        cards_grid.addWidget(self._card_matched[0],    0, 1)
        cards_grid.addWidget(self._card_rms_blue[0],   1, 0)
        cards_grid.addWidget(self._card_rms_red[0],    1, 1)
        rs_lay.addWidget(cards_widget)
        cov_row = QWidget()
        cov_lay = QHBoxLayout(cov_row)
        cov_lay.setContentsMargins(0, 0, 0, 0)
        cov_lbl = QLabel("Coverage:")
        cov_lbl.setStyleSheet(f"color:{TEXT_DIM}; font-size:{F_SM}; border:none;")
        self._coverage_bar = CoverageBar()
        cov_lay.addWidget(cov_lbl)
        cov_lay.addWidget(self._coverage_bar, stretch=1)
        rs_lay.addWidget(cov_row)
        self._poly_order_label = QLabel("Polynomial order: —")
        self._poly_order_label.setStyleSheet(
            f"color:{TEXT_DIM}; font-size:{F_SM}; border:none;")
        rs_lay.addWidget(self._poly_order_label)
        self._rms_caveat_label = QLabel("RMS reflects centroiding accuracy")
        self._rms_caveat_label.setStyleSheet(
            f"color:{TEXT_DIM}; font-size:9pt; border:none;")
        rs_lay.addWidget(self._rms_caveat_label)
        right_col.addWidget(self._result_section)
        self._result_section.setVisible(False)

        # Error panel
        self._error_panel = QFrame()
        ep_lay = QVBoxLayout(self._error_panel)
        ep_lay.setContentsMargins(4, 4, 4, 4)
        self._error_label = QLabel("")
        self._error_label.setStyleSheet(f"color:{WARN}; border:none;")
        self._error_label.setWordWrap(True)
        ep_lay.addWidget(self._error_label)
        right_col.addWidget(self._error_panel)
        self._error_panel.setVisible(False)

        # Save button
        self._save_btn = QPushButton("Save → wavelength_cal.json")
        self._save_btn.clicked.connect(self._on_save)
        self._save_btn.setEnabled(False)
        right_col.addWidget(self._save_btn)
        right_col.addStretch()
        root.addWidget(right_widget, stretch=1)

    def _make_metric_card(self, label_text: str, value_text: str):
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background:{DARK_PANEL}; border:1px solid {DARK_BORDER}; "
            f"border-radius:3px; }}")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(1)
        lbl = QLabel(label_text)
        lbl.setStyleSheet(f"color:{TEXT_DIM}; font-size:9pt; border:none;")
        val = QLabel(value_text)
        val.setStyleSheet(
            f"color:{OK_COL}; font-size:{F_BASE}; font-weight:bold; border:none;")
        lay.addWidget(lbl)
        lay.addWidget(val)
        return frame, lbl, val

    def set_region(self, y_lo: int, y_hi: int):
        self._ylo_spin.blockSignals(True)
        self._yhi_spin.blockSignals(True)
        self._ylo_spin.setValue(y_lo)
        self._yhi_spin.setValue(y_hi)
        self._ylo_spin.blockSignals(False)
        self._yhi_spin.blockSignals(False)
        self._image_canvas.set_region(y_lo, y_hi)

    def _on_canvas_region_changed(self, y_lo: int, y_hi: int):
        self._ylo_spin.blockSignals(True)
        self._yhi_spin.blockSignals(True)
        self._ylo_spin.setValue(y_lo)
        self._yhi_spin.setValue(y_hi)
        self._ylo_spin.blockSignals(False)
        self._yhi_spin.blockSignals(False)

    def _on_region_spin_changed(self):
        y_lo = self._ylo_spin.value()
        y_hi = self._yhi_spin.value()
        self._image_canvas.set_region(y_lo, y_hi)
        if self._data is not None:
            self._refresh_spectrum()

    def _on_mode_changed(self, mode_id: int):
        self._lamp_panel.setVisible(mode_id == 0)
        self._balmer_panel.setVisible(mode_id == 1)
        self._spec_canvas.enable_span_selector(mode_id == 1)

    def _on_lamp_changed(self):
        lamp_key = self._lamp_combo.currentData()
        if lamp_key:
            warn = LAMP_LINES.get(lamp_key, {}).get("warn")
            self._warn_label.setText(warn or "")

    def _on_load_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Calibration Image", "",
            "FITS files (*.fits *.fit);;All files (*)"
        )
        if not path:
            return
        try:
            with pyfits.open(path) as hdul:
                raw = hdul[0].data
            if raw is None:
                self._warn_label.setText("No image data in FITS file.")
                return
            self._data = raw.astype(np.float32)
            self._cal_path = Path(path)
            self._file_lbl.setText(Path(path).name)
            self._image_canvas.load(self._data)
            slant = detect_slant(self._data,
                                  self._ylo_spin.value(), self._yhi_spin.value())
            self._last_slant = slant
            self._slant_val_label.setText(f"{slant:+.2f}°")
            self._image_canvas._slant_deg = slant
            self._image_canvas.refresh()
            self._refresh_spectrum()
            self._solve_btn.setEnabled(True)
            self._warn_label.setText("")
            self._on_lamp_changed()
        except Exception as e:
            self._warn_label.setText(f"Error loading file: {e}")

    def _refresh_spectrum(self):
        if self._data is None:
            return
        y_lo = self._ylo_spin.value()
        y_hi = self._yhi_spin.value()
        slant = self._last_slant if self._slant_apply_chk.isChecked() else 0.0
        self._spectrum = extract_cal_spectrum(self._data, y_lo, y_hi, slant_deg=slant)
        self._spec_canvas.refresh(self._spectrum)

    def _on_solve(self):
        if self._data is None:
            return
        lamp_key = self._lamp_combo.currentData()
        y_lo = self._ylo_spin.value()
        y_hi = self._yhi_spin.value()

        slant = detect_slant(self._data, y_lo, y_hi)
        self._last_slant = slant
        self._slant_val_label.setText(f"{slant:+.2f}°")
        self._image_canvas._slant_deg = slant
        self._image_canvas.refresh()

        spectrum = extract_cal_spectrum(
            self._data, y_lo, y_hi,
            slant_deg=slant if self._slant_apply_chk.isChecked() else 0.0,
        )
        self._spectrum = spectrum
        self._spec_canvas.refresh(spectrum)

        result = auto_solve_lamp(spectrum, lamp_key)

        if result is None or result.get("n_matched", 0) < 4:
            peaks = detect_emission_peaks(spectrum)
            n_found = result.get("n_matched", 0) if result else 0
            if len(peaks) < 3:
                msg = "No signal — increase exposure or check lamp type."
            elif len(peaks) > 80:
                msg = "Overexposed — too many false peaks. Reduce exposure."
            else:
                msg = (f"Poor solution ({n_found} lines matched). "
                       f"Check lamp type or Y-region.")
            self._error_label.setText(msg)
            self._error_panel.setVisible(True)
            self._result_section.setVisible(False)
            return

        self._cal = WavelengthCalibration(
            coef        = result["coef"].tolist(),
            poly_order  = result["poly_order"],
            rms_global  = result["rms_global"],
            rms_blue    = result["rms_blue"],
            rms_red     = result["rms_red"],
            n_matched   = result["n_matched"],
            n_total     = result["n_total"],
            lambda_min  = result["lambda_min"],
            lambda_max  = result["lambda_max"],
            slant_deg   = slant,
            lamp_type   = lamp_key,
            source_file = str(self._cal_path),
            timestamp   = datetime.now().isoformat(timespec='seconds'),
        )
        self._matched_pairs = result["matched_pairs"]
        self._spec_canvas.refresh(spectrum, matched_pairs=self._matched_pairs)
        self._res_canvas.refresh(self._matched_pairs, result["coef"])
        self._update_result_widgets()
        self._save_btn.setEnabled(True)
        self._error_panel.setVisible(False)
        self._result_section.setVisible(True)

    def _on_span_selected(self, px_min: float, px_max: float):
        if self._spectrum is None:
            return
        x = np.arange(len(self._spectrum))
        mask = (x >= px_min) & (x <= px_max)
        if mask.sum() < 5:
            return
        centroid_px = fit_gaussian_absorption(x[mask].astype(float),
                                               self._spectrum[mask])
        if centroid_px is None:
            return
        self._pending_px = centroid_px

    def _on_assign_balmer(self):
        if self._pending_px is None:
            return
        idx = self._line_combo.currentIndex()
        name, wave = STELLAR_LINES[idx]
        self._balmer_pairs.append((self._pending_px, wave, name))
        self._balmer_list.addItem(
            f"{name}  {wave:.2f} Å  @ px {self._pending_px:.1f}")
        self._pending_px = None
        if len(self._balmer_pairs) >= 2:
            self._fit_balmer()

    def _on_clear_balmer(self):
        self._balmer_pairs.clear()
        self._balmer_list.clear()
        self._pending_px = None
        self._result_section.setVisible(False)

    def _fit_balmer(self):
        px_arr  = np.array([p[0] for p in self._balmer_pairs])
        wav_arr = np.array([p[1] for p in self._balmer_pairs])
        coef    = _fit_best_order(px_arr, wav_arr)
        n       = len(self._balmer_pairs)
        fitted  = np.polyval(coef, px_arr)
        resid   = wav_arr - fitted
        rms_note = ""
        if n <= len(coef):
            rms_note   = f"exact fit ({n} tie points — RMS meaningless)"
            rms_global = 0.0
        else:
            rms_global = float(np.sqrt(np.mean(resid ** 2)))
        blue_mask = wav_arr < 5500
        red_mask  = ~blue_mask
        rms_blue = float(np.sqrt(np.mean(resid[blue_mask] ** 2))) if blue_mask.any() else float('nan')
        rms_red  = float(np.sqrt(np.mean(resid[red_mask]  ** 2))) if red_mask.any()  else float('nan')
        self._cal = WavelengthCalibration(
            coef        = coef.tolist(),
            poly_order  = len(coef) - 1,
            rms_global  = rms_global,
            rms_blue    = rms_blue,
            rms_red     = rms_red,
            n_matched   = n,
            n_total     = n,
            lambda_min  = float(wav_arr.min()),
            lambda_max  = float(wav_arr.max()),
            slant_deg   = self._last_slant,
            lamp_type   = "Balmer",
            source_file = str(self._cal_path) if self._cal_path else "",
            timestamp   = datetime.now().isoformat(timespec='seconds'),
        )
        self._matched_pairs = [(px_arr[i], wav_arr[i], self._balmer_pairs[i][2])
                               for i in range(n)]
        self._res_canvas.refresh(self._matched_pairs, coef)
        self._update_result_widgets()
        if rms_note:
            self._rms_caveat_label.setText(rms_note)
        self._save_btn.setEnabled(True)
        self._error_panel.setVisible(False)
        self._result_section.setVisible(True)

    def _update_result_widgets(self):
        if self._cal is None:
            return
        rms = self._cal.rms_global
        rms_col = OK_COL if rms < 0.8 else WARN
        self._card_rms_global[2].setText(f"{rms:.3f} Å")
        self._card_rms_global[2].setStyleSheet(
            f"color:{rms_col}; font-size:{F_BASE}; font-weight:bold; border:none;")
        self._card_matched[2].setText(
            f"{self._cal.n_matched}/{self._cal.n_total}")
        # Blue RMS
        if np.isnan(self._cal.rms_blue):
            self._card_rms_blue[0].setStyleSheet(
                f"QFrame {{ background:{DARK_BORDER}; border:1px solid {DARK_BORDER};"
                f" border-radius:3px; }}")
            self._card_rms_blue[2].setText("N/A")
            self._card_rms_blue[2].setStyleSheet(
                f"color:{WARN}; font-size:{F_BASE}; font-weight:bold; border:none;")
        else:
            col = OK_COL if self._cal.rms_blue < 0.8 else WARN
            self._card_rms_blue[2].setText(f"{self._cal.rms_blue:.3f} Å")
            self._card_rms_blue[2].setStyleSheet(
                f"color:{col}; font-size:{F_BASE}; font-weight:bold; border:none;")
        # Red RMS
        if np.isnan(self._cal.rms_red):
            self._card_rms_red[0].setStyleSheet(
                f"QFrame {{ background:{DARK_BORDER}; border:1px solid {DARK_BORDER};"
                f" border-radius:3px; }}")
            self._card_rms_red[2].setText("N/A")
            self._card_rms_red[2].setStyleSheet(
                f"color:{WARN}; font-size:{F_BASE}; font-weight:bold; border:none;")
        else:
            col = OK_COL if self._cal.rms_red < 0.8 else WARN
            self._card_rms_red[2].setText(f"{self._cal.rms_red:.3f} Å")
            self._card_rms_red[2].setStyleSheet(
                f"color:{col}; font-size:{F_BASE}; font-weight:bold; border:none;")
        self._coverage_bar.set_range(self._cal.lambda_min, self._cal.lambda_max)
        self._poly_order_label.setText(
            f"Polynomial order: {self._cal.poly_order}")
        self._rms_caveat_label.setText("RMS reflects centroiding accuracy")

    def _on_save(self):
        if self._cal is None:
            return
        cal_path = Path(__file__).parent / "wavelength_cal.json"
        try:
            with open(cal_path, "w") as f:
                json.dump(self._cal.to_dict(), f, indent=2)
            self._warn_label.setText("Saved ✓")
        except Exception as e:
            self._warn_label.setText(f"Save error: {e}")


# ── Main window ────────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg         = load_config()
        self.fits_data   = None
        self._rotated_data: np.ndarray | None = None
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
        self._logbook_region_timer = QTimer(self)
        self._logbook_region_timer.setSingleShot(True)
        self._logbook_region_timer.setInterval(2000)
        self._logbook_region_timer.timeout.connect(self._write_regions_to_logbook)

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

        # Create header-row controls before section_box so they can be injected
        _hsep1 = QFrame(); _hsep1.setFrameShape(QFrame.Shape.VLine)
        _hsep1.setStyleSheet(f"QFrame {{ color:{DARK_BORDER}; max-width:1px; }}")
        self.radio_latest = QRadioButton("Latest")
        self.radio_hold   = QRadioButton("Hold")
        self.radio_latest.setChecked(True)
        _rgrp = QButtonGroup(self)
        _rgrp.addButton(self.radio_latest)
        _rgrp.addButton(self.radio_hold)
        self.radio_latest.toggled.connect(self._on_view_mode_changed)
        _hsep2 = QFrame(); _hsep2.setFrameShape(QFrame.Shape.VLine)
        _hsep2.setStyleSheet(f"QFrame {{ color:{DARK_BORDER}; max-width:1px; }}")
        self.btn_theme = QPushButton("Day Mode")
        self.btn_theme.setCheckable(True)
        self.btn_theme.setFixedWidth(110)
        self.btn_theme.setToolTip(
            "Switch between night-vision (red) and day (blue) colour schemes")
        self.btn_theme.toggled.connect(self._on_theme_toggle)
        self._header_seps = [_hsep1, _hsep2]

        img_grp, img_lay = section_box(
            "Latest FITS Image", "image",
            header_extra=[_hsep1, self.radio_latest, self.radio_hold,
                          _hsep2, self.btn_theme])
        self._img_title_lbl = _section_titles[-1]  # capture for Hold/Latest rename
        self.img_canvas = ImageCanvas()
        self.img_canvas.line_released.connect(self._on_lines_released)
        self.img_canvas.zoom_x_changed.connect(self._on_zoom_x_changed)
        self.img_canvas.zoom_reset_sig.connect(self._on_zoom_reset_sync)
        self.lbl_filename = QLabel("No file loaded")
        self.lbl_filename.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_filename.setStyleSheet(
            f"color:{ACCENT}; font-size:{F_SM}; border:none;")
        img_lay.addWidget(self.lbl_filename)
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
        stretch_lbl.setStyleSheet(f"color:{ACCENT}; font-size:{F_BASE}; border:none;")
        self._stretch_lbl = stretch_lbl
        tl.addWidget(stretch_lbl)
        self.stretch_slider = QSlider(Qt.Orientation.Horizontal)
        self.stretch_slider.setRange(1, 10)
        self.stretch_slider.setFixedWidth(90)
        self.stretch_slider.valueChanged.connect(self._on_stretch)
        tl.addWidget(self.stretch_slider)

        rot_sep = QFrame()
        rot_sep.setFrameShape(QFrame.Shape.VLine)
        rot_sep.setStyleSheet(f"QFrame {{ color:{DARK_BORDER}; max-width:1px; }}")
        self._rot_sep = rot_sep
        tl.addWidget(rot_sep)

        rot_lbl = QLabel("Rotate°:")
        rot_lbl.setStyleSheet(f"color:{ACCENT}; font-size:{F_BASE}; border:none;")
        self._rot_lbl = rot_lbl
        tl.addWidget(rot_lbl)

        self.spin_rotate = QDoubleSpinBox()
        self.spin_rotate.setRange(-5.0, 5.0)
        self.spin_rotate.setDecimals(3)
        self.spin_rotate.setSingleStep(0.1)
        self.spin_rotate.setValue(self.cfg.get("rotation_angle", 0.0))
        self.spin_rotate.setFixedWidth(90)
        self.spin_rotate.setToolTip(
            "Rotate image ±5° to align spectral trace with extraction bands.\n"
            "Arrow keys: ±0.01°  |  Manual entry: any precision down to 0.001°\n"
            "Uses bicubic spline interpolation (scipy order=3, reflect borders).")
        self.spin_rotate.valueChanged.connect(self._on_rotate_changed)
        tl.addWidget(self.spin_rotate)
        tl.addWidget(_arrow_btns(self.spin_rotate))

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
        self.spec_canvas.zoom_x_changed.connect(self._on_spec_zoom_x_changed)
        spec_lay.addWidget(self.spec_canvas)

        spec_zoom_row = QWidget()
        szl = QHBoxLayout(spec_zoom_row)
        szl.setContentsMargins(0, 0, 0, 0)
        szl.setSpacing(4)
        self.btn_spec_zoom = QPushButton("⊕ Zoom")
        self.btn_spec_zoom.setCheckable(True)
        self.btn_spec_zoom.setFixedWidth(78)
        self.btn_spec_zoom.setToolTip("Click and drag a rectangle on the spectrum to zoom in")
        self.btn_spec_zoom.toggled.connect(self._on_spec_zoom_toggle)
        self.btn_spec_reset_zoom = QPushButton("↺ Reset")
        self.btn_spec_reset_zoom.setFixedWidth(78)
        self.btn_spec_reset_zoom.setToolTip("Restore full spectrum and image view")
        self.btn_spec_reset_zoom.clicked.connect(self._on_spec_zoom_reset)
        self.btn_spec_zoom_range = QPushButton("Zoom to range")
        self.btn_spec_zoom_range.setToolTip(
            "Zoom Y so the target peak is at 80% of the visible scale")
        self.btn_spec_zoom_range.clicked.connect(self._on_spec_zoom_to_range)
        szl.addWidget(self.btn_spec_zoom)
        szl.addWidget(self.btn_spec_reset_zoom)
        szl.addWidget(self.btn_spec_zoom_range)
        szl.addStretch()
        spec_lay.addWidget(spec_zoom_row)

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
        self.lbl_folder.setStyleSheet(f"color:{ACCENT}; font-size:{F_SM};")
        self.lbl_folder.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.lbl_fileinfo = QLabel("")
        self.lbl_fileinfo.setStyleSheet(f"color:{TEXT_DIM}; font-size:{F_SM};")

        filter_lbl = QLabel("Filter:")
        filter_lbl.setStyleSheet(f"color:{ACCENT}; font-size:{F_BASE}; border:none;")
        self._filter_lbl = filter_lbl
        self.txt_filter = QLineEdit()
        self.txt_filter.setPlaceholderText("*alfCyg*")
        self.txt_filter.setFixedWidth(150)
        self.txt_filter.setToolTip(
            "Filename glob filter — only FITS files whose names match this pattern are shown.\n"
            "Examples: *alfCyg*   betPer_*.fits   Leave blank to match all files.")
        self.txt_filter.textChanged.connect(self._on_filter_changed)

        self._vline_seps = []

        # File count label — right of filter box, bright ACCENT colour
        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet(f"color:{ACCENT}; font-size:{F_SM};")

        for w in (self.btn_folder, self.btn_step, self.lbl_folder,
                  self.lbl_fileinfo, filter_lbl, self.txt_filter, self.lbl_count):
            bl.addWidget(w)

        rl.addWidget(bottom)

        # Wire the Gain Advice button created inside AdvisoryPanel
        self.btn_gain = self.advisory.btn_gain
        self.btn_gain.setChecked(self._gain_on)
        self.btn_gain.toggled.connect(self._on_gain_toggle)
        self._update_gain_btn_label()

        # ── Status bar (errors / transient messages only) ──────────────────────
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.sb_file = QLabel("")
        self.sb_file.setStyleSheet(f"font-size:{F_SM};")
        sb.addWidget(self.sb_file, 1)

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
        if self.cfg.get("watch_folder"):
            self.lbl_folder.setText(self.cfg["watch_folder"])
        self.txt_filter.setText(self.cfg.get("file_filter", ""))
        self.spin_rotate.setValue(self.cfg.get("rotation_angle", 0.0))

    def _ui_to_cfg(self):
        self.cfg["target_y_start"],   self.cfg["target_y_end"]   = \
            self.ctrl_target.get_values()
        self.cfg["bg_above_y_start"], self.cfg["bg_above_y_end"] = \
            self.ctrl_bg_above.get_values()
        self.cfg["bg_below_y_start"], self.cfg["bg_below_y_end"] = \
            self.ctrl_bg_below.get_values()
        self.cfg["stretch_value"]      = self.stretch_slider.value()
        self.cfg["gain_advice_on"]     = self._gain_on

    def _spinboxes_from_canvas(self):
        r = self.img_canvas.get_region()
        self.ctrl_target.set_values(r["tgt_top"], r["tgt_bot"])
        self.ctrl_bg_above.set_values(r["bga_top"], r["bga_bot"])
        self.ctrl_bg_below.set_values(r["bgb_top"], r["bgb_bot"])

    def _cfg_from_canvas(self):
        self.img_canvas.region_to_cfg(self.cfg)
        self.cfg["stretch_value"]      = self.stretch_slider.value()

    def _fmt_count(self) -> str:
        """Return 'N/T file(s)' where N=filtered count, T=total FITS in folder."""
        if not self.watcher:
            return ""
        n = self.watcher.count()
        t = self.watcher.total_count()
        if self.cfg.get("file_filter", "") and n != t:
            return f"{n}/{t} file(s)"
        return f"{t} file(s)"

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

    def _on_filter_changed(self, pattern: str):
        self.cfg["file_filter"] = pattern
        save_config(self.cfg)
        if self.watcher:
            self.watcher.apply_filter(pattern)
            self.lbl_count.setText(self._fmt_count())
            if self.watcher.latest():
                self._load_file(self.watcher.latest())
            else:
                self._clear_display()

    def _start_watcher(self, folder):
        if self.watcher:
            self.watcher.stop()
            self.watcher.wait(600)

        # Always start a fresh session when changing / re-opening a folder
        self.session_data      = SessionData()
        self._last_cont_mask   = None

        self.watcher = FolderWatcher(
            folder, self.cfg.get("poll_interval_ms", 2000),
            self.cfg.get("file_filter", ""))
        self.watcher.new_file_found.connect(self._on_new_file)
        self.watcher.start()
        self.lbl_count.setText(self._fmt_count())

        if self.watcher.latest():
            self._load_file(self.watcher.latest())
        else:
            self._clear_display()

    def _clear_display(self):
        """Reset all panels to empty state (no FITS data)."""
        self.fits_data      = None
        self._rotated_data  = None
        self._spec          = None
        self._bg        = None
        self._n_target  = 1
        self._cur_file  = ""
        self.setWindowTitle("Spectro Inspector")
        self.sb_file.setText("")
        self.lbl_filename.setText("No file loaded")
        self.lbl_fileinfo.setText("")
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
        filter_pat = self.cfg.get("file_filter", "")
        if filter_pat:
            files = [f for f in files if fnmatch.fnmatch(f.name, filter_pat)]
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
        self.lbl_count.setText(f"Stepping: {self._step_idx} / {total}")
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
            self.lbl_count.setText(self._fmt_count() + " — live")

    def _stop_step_through(self):
        if self._step_timer:
            self._step_timer.stop()
        self._finish_step_through()

    def _on_new_file(self, path):
        if self.watcher:
            self.lbl_count.setText(self._fmt_count())
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

        self._apply_rotation()
        self._refresh_all()
        self._process_session_frame()

        self.sb_file.setText("")
        self.lbl_filename.setText(d["filename"])
        self.lbl_fileinfo.setText(self._file_info_text(d))

    # ── rotation ─────────────────────────────────────────────────────────────
    def _apply_rotation(self):
        if self.fits_data is None:
            self._rotated_data = None
            return
        angle = self.cfg.get("rotation_angle", 0.0)
        self._rotated_data = rotate_image(self.fits_data["data"], angle)

    def _effective_fits(self) -> dict | None:
        """Return fits_data with 'data' replaced by the cached rotated array."""
        if self.fits_data is None:
            return None
        if self._rotated_data is not None:
            d = dict(self.fits_data)
            d["data"] = self._rotated_data
            return d
        return self.fits_data

    # ── refresh ───────────────────────────────────────────────────────────────
    def _refresh_all(self):
        if self._busy: return
        self._busy = True
        try:
            self._ui_to_cfg()
            self.img_canvas.refresh(self._effective_fits(), self.cfg, self.stretch_slider.value())
            self._refresh_spec_advisory()
        finally:
            self._busy = False

    def _refresh_spec_advisory(self):
        res = self.spec_canvas.refresh(
            self._effective_fits(), self.cfg)
        if res is not None:
            _, self._spec, self._bg, self._n_target = res
        self.advisory.refresh_data(
            self._effective_fits(), self.cfg,
            self._spec, self._bg, self._n_target,
            gain_on=self._gain_on)

    # ── signal handlers ───────────────────────────────────────────────────────
    def _on_view_mode_changed(self, latest: bool):
        self._hold = not latest
        self._img_title_lbl.setText(
            "Latest FITS Image" if latest else "HOLD FITS Image")

    def _on_rotate_changed(self, value: float):
        self.cfg["rotation_angle"] = round(value, 4)
        save_config(self.cfg)
        self._apply_rotation()
        self._refresh_all()

    def _on_lines_released(self):
        self._cfg_from_canvas()
        self._spinboxes_from_canvas()
        save_config(self.cfg)
        self._refresh_spec_advisory()

    def _on_regions_changed(self):
        self._ui_to_cfg()
        save_config(self.cfg)
        self._refresh_all()
        self._logbook_region_timer.start()

    def _write_regions_to_logbook(self):
        c = self.cfg
        self.logbook.append_note(
            f"[regions] TARGET y {c['target_y_start']}–{c['target_y_end']}  "
            f"BG_ABOVE y {c['bg_above_y_start']}–{c['bg_above_y_end']}  "
            f"BG_BELOW y {c['bg_below_y_start']}–{c['bg_below_y_end']}"
        )

    def _on_stretch(self):
        self._ui_to_cfg()
        save_config(self.cfg)
        self.img_canvas.refresh(self._effective_fits(), self.cfg, self.stretch_slider.value())

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
        self.spec_canvas.reset_zoom()
        self.session_monitor.conv_panel.reset_xrange()

    def _on_spec_zoom_toggle(self, checked):
        self.spec_canvas.set_zoom_mode(checked)

    def _on_spec_zoom_reset(self):
        self.btn_spec_zoom.setChecked(False)
        self.spec_canvas.reset_zoom()
        self.img_canvas.reset_zoom()
        self.session_monitor.conv_panel.reset_xrange()

    def _on_spec_zoom_to_range(self):
        self.spec_canvas.zoom_to_data_range()

    def _on_zoom_x_changed(self, x_min: float, x_max: float):
        self.spec_canvas.set_xrange(x_min, x_max)
        self.session_monitor.conv_panel.set_xrange(x_min, x_max)

    def _on_spec_zoom_x_changed(self, x_min: float, x_max: float):
        self.img_canvas.set_xrange(x_min, x_max)
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
        data = self._rotated_data if self._rotated_data is not None else self.fits_data["data"]
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
        spatial = None
        if n_cont >= 10:
            spatial = _spatial_profile_from_continuum(data, cont_mask, y0_prof, y1_prof)
            if spatial is not None:
                fwhm, _centroid, reliable = fit_gaussian_spatial(
                    spatial,
                    residual_threshold=cfg.get("gaussian_residual_thresh", 0.30),
                )

        # New slit-quality metrics
        spatial_centroid = _centroid
        profile_asymmetry = None
        if spatial is not None and _centroid is not None:
            ci    = max(1, min(int(round(float(_centroid))), len(spatial) - 1))
            above = float(np.sum(spatial[:ci]))
            below = float(np.sum(spatial[ci:]))
            denom = above + below
            profile_asymmetry = (above - below) / denom if denom > 0 else None
        total_flux = float(np.sum(spec)) if spec is not None else None

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
            fwhm_px           = fwhm,
            fwhm_reliable     = reliable,
            n_continuum       = n_cont,
            spatial_centroid  = spatial_centroid,
            profile_asymmetry = profile_asymmetry,
            total_flux        = total_flux,
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
        """Frame Manager double-click — switch to Hold mode and display that frame."""
        self.radio_hold.setChecked(True)   # sets self._hold = True via signal
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
        self._apply_rotation()
        self._refresh_all()
        self.sb_file.setText("")
        self.lbl_filename.setText(f"[viewing] {d['filename']}")
        self.lbl_fileinfo.setText(self._file_info_text(d))

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
        for sep in self._header_seps:
            sep.setStyleSheet(
                "" if day else f"QFrame {{ color:{DARK_BORDER}; max-width:1px; }}")
        self.lbl_folder.setStyleSheet(
            "" if day else f"color:{ACCENT}; font-size:{F_SM};")
        self.lbl_filename.setStyleSheet(
            "" if day else f"color:{ACCENT}; font-size:{F_SM}; border:none;")
        self._filter_lbl.setStyleSheet(
            "" if day else f"color:{ACCENT}; font-size:{F_BASE}; border:none;")

        # Stretch label + rotate label/separator
        self._stretch_lbl.setStyleSheet(
            "" if day else f"color:{ACCENT}; font-size:{F_BASE}; border:none;")
        self._rot_lbl.setStyleSheet(
            "" if day else f"color:{ACCENT}; font-size:{F_BASE}; border:none;")
        self._rot_sep.setStyleSheet(
            "" if day else f"QFrame {{ color:{DARK_BORDER}; max-width:1px; }}")

        # Bottom bar file info + count label
        self.lbl_fileinfo.setStyleSheet(
            "" if day else f"color:{TEXT_DIM}; font-size:{F_SM};")
        self.lbl_count.setStyleSheet(
            "" if day else f"color:{ACCENT}; font-size:{F_SM};")

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

        # Region controls (dot/label + arrow buttons)
        for ctrl in (self.ctrl_target, self.ctrl_bg_above, self.ctrl_bg_below):
            ctrl._restyle()
        # All ▲/▼ spinbox arrow buttons (registered globally by _arrow_btns())
        _ab_sty = (f"font-size:9pt; padding:0px; color:{DARK_BG}; "
                   f"background:{TEXT_HI}; border:1px solid {DARK_BORDER};")
        for btn in _arrow_btns_list:
            btn.setStyleSheet("" if day else _ab_sty)

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
def _qt_msg_handler(mode, context, message):
    """Suppress noisy Qt startup warnings (e.g. cursor-position before window shown)."""
    if "cursor position" in message.lower():
        return
    import sys as _sys
    print(message, file=_sys.stderr)

def main():
    from PyQt6.QtCore import qInstallMessageHandler
    qInstallMessageHandler(_qt_msg_handler)
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

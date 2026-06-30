"""
ui_kit.py
---------
Presentation helpers for the FIAA dashboard: the command-center theme,
Indian-currency formatting, the SVG risk gauge and reusable HTML cards.
Kept separate from app.py so the page file stays readable.
"""
from __future__ import annotations

# ---- colour system (fraud SOC / command-center) --------------------------
INK      = "#0B1220"   # page background
SURFACE  = "#131E36"   # panel
SURFACE2 = "#0F1830"   # inset
LINE     = "#243352"   # hairline border
TEXT     = "#E7EEFA"   # primary text
MUTED    = "#8DA0C0"   # secondary text
CYAN     = "#27E0E8"   # primary / active signal
AMBER    = "#F6A53B"   # warning
CRIMSON  = "#FF4D6D"   # high risk
MINT     = "#37E0A6"   # safe / auto-close
VIOLET   = "#9A8CFF"   # supervisor / accent


def inr(amount) -> str:
    """Format a number in the Indian grouping system: 4,87,000."""
    try:
        n = int(round(float(amount)))
    except (TypeError, ValueError):
        return str(amount)
    s = str(abs(n))
    if len(s) <= 3:
        grouped = s
    else:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:]); head = head[:-2]
        if head:
            parts.insert(0, head)
        grouped = ",".join(parts) + "," + tail
    return ("-" if n < 0 else "") + grouped


def risk_band(score: float) -> tuple[str, str]:
    """Return (label, colour) for a 1-10 risk score."""
    if score >= 7:
        return "HIGH", CRIMSON
    if score >= 4:
        return "ELEVATED", AMBER
    return "LOW", MINT


def gauge_svg(score: float, size: int = 168) -> str:
    """A clean SVG donut gauge for the 1-10 risk score."""
    score = max(0.0, min(10.0, float(score)))
    _, colour = risk_band(score)
    r = size / 2 - 14
    cx = cy = size / 2
    circ = 2 * 3.14159 * r
    frac = score / 10.0
    dash = circ * frac
    return f"""
    <svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">
      <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{LINE}" stroke-width="12"/>
      <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{colour}" stroke-width="12"
              stroke-linecap="round" stroke-dasharray="{dash} {circ}"
              transform="rotate(-90 {cx} {cy})"/>
      <text x="{cx}" y="{cy-2}" text-anchor="middle" dominant-baseline="middle"
            font-family="'JetBrains Mono',monospace" font-size="40" font-weight="700"
            fill="{TEXT}">{score:.1f}</text>
      <text x="{cx}" y="{cy+26}" text-anchor="middle" font-family="Inter,sans-serif"
            font-size="11" letter-spacing="2" fill="{MUTED}">RISK / 10</text>
    </svg>"""


def css() -> str:
    return f"""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;700&display=swap');

      .stApp {{ background:
        radial-gradient(1200px 600px at 80% -10%, #16243f 0%, {INK} 55%) fixed; }}

      /* --- FIX: keep the page heading from hiding under Streamlit's top bar --
         The default toolbar (Deploy / ⋮) floats over the content. We make it
         transparent and push the main content down so the masthead title is
         always fully visible. */
      header[data-testid="stHeader"] {{ background: transparent; }}
      div[data-testid="stToolbar"] {{ right: 0.5rem; }}
      .block-container {{ padding-top: 3.6rem; max-width: 1180px; }}

      html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; color: {TEXT}; }}

      /* sidebar */
      section[data-testid="stSidebar"] {{ background: {SURFACE2}; border-right: 1px solid {LINE}; }}

      /* masthead */
      .fiaa-mast {{ display:flex; align-items:center; gap:14px; margin-bottom:4px; }}
      .fiaa-logo {{ width:42px;height:42px;border-radius:11px;
        background: linear-gradient(135deg,{CYAN},{VIOLET});
        display:flex;align-items:center;justify-content:center;font-weight:700;
        font-size:20px;color:{INK}; box-shadow:0 6px 22px rgba(39,224,232,.25); }}
      .fiaa-title {{ font-size:23px; font-weight:700; letter-spacing:.2px;
        line-height:1.3; padding-right:8px; }}
      .fiaa-sub {{ color:{MUTED}; font-size:12.5px; letter-spacing:.4px;
        text-transform:uppercase; line-height:1.4; }}

      /* generic panel */
      .panel {{ background:{SURFACE}; border:1px solid {LINE}; border-radius:16px;
        padding:18px 20px; margin-bottom:14px; }}

      /* hero alert */
      .hero {{ background: linear-gradient(180deg,{SURFACE} 0%, {SURFACE2} 100%);
        border:1px solid {LINE}; border-radius:18px; padding:22px 24px; position:relative;
        overflow:hidden; }}
      .hero .strip {{ position:absolute; left:0; top:0; bottom:0; width:5px; }}
      .amount {{ font-family:'JetBrains Mono',monospace; font-weight:700;
        font-size:52px; line-height:1; }}
      .amount .cur {{ font-size:24px; color:{MUTED}; margin-right:8px; }}
      .kicker {{ font-size:11px; letter-spacing:2.5px; text-transform:uppercase;
        color:{MUTED}; }}
      .meta-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px;
        margin-top:18px; }}
      .meta-grid .lbl {{ font-size:10.5px; letter-spacing:1.5px; text-transform:uppercase;
        color:{MUTED}; }}
      .meta-grid .val {{ font-size:15px; font-weight:600; margin-top:2px;
        font-family:'JetBrains Mono',monospace; }}

      /* signal chips */
      .chip {{ display:inline-block; padding:4px 11px; border-radius:999px;
        font-size:11.5px; font-weight:600; margin:3px 6px 3px 0;
        border:1px solid {LINE}; background:{SURFACE2}; color:{TEXT}; }}
      .chip.warn {{ border-color:{AMBER}; color:{AMBER}; }}
      .chip.hot {{ border-color:{CRIMSON}; color:{CRIMSON}; }}

      /* badges */
      .badge {{ display:inline-block; padding:5px 13px; border-radius:9px;
        font-size:12px; font-weight:700; letter-spacing:.4px; }}
      .badge.hi {{ background:rgba(255,77,109,.14); color:{CRIMSON};
        border:1px solid rgba(255,77,109,.4); }}
      .badge.lo {{ background:rgba(55,224,166,.14); color:{MINT};
        border:1px solid rgba(55,224,166,.4); }}
      .badge.re {{ background:rgba(246,165,59,.14); color:{AMBER};
        border:1px solid rgba(246,165,59,.4); }}

      /* alert inbox row */
      .alert-row {{ display:flex; justify-content:space-between; align-items:center;
        background:{SURFACE}; border:1px solid {LINE}; border-radius:13px;
        padding:14px 16px; margin-bottom:10px; transition:border-color .15s; }}
      .alert-row:hover {{ border-color:{CYAN}; }}
      .alert-amt {{ font-family:'JetBrains Mono',monospace; font-weight:700; font-size:20px; }}
      .alert-id {{ font-family:'JetBrains Mono',monospace; font-size:12px; color:{MUTED}; }}

      /* evidence + tables */
      .ev {{ border-left:3px solid {LINE}; padding:8px 0 8px 14px; margin-bottom:8px; }}
      .ev.high {{ border-color:{CRIMSON}; }}
      .ev.med {{ border-color:{AMBER}; }}
      .ev.low {{ border-color:{MINT}; }}
      .ev .src {{ font-size:10.5px; color:{MUTED}; text-transform:uppercase;
        letter-spacing:1px; }}

      /* metric tiles */
      .tile {{ background:{SURFACE}; border:1px solid {LINE}; border-radius:14px;
        padding:16px 18px; }}
      .tile .big {{ font-family:'JetBrains Mono',monospace; font-size:30px;
        font-weight:700; }}
      .tile .cap {{ font-size:11px; color:{MUTED}; letter-spacing:1px;
        text-transform:uppercase; }}

      /* timeline step */
      .step {{ display:flex; gap:12px; align-items:flex-start; margin-bottom:10px; }}
      .step .dot {{ width:11px;height:11px;border-radius:50%;margin-top:5px;flex:none;
        background:{CYAN}; box-shadow:0 0 0 4px rgba(39,224,232,.12); }}
      .step .who {{ font-weight:600; font-size:13.5px; }}
      .step .what {{ color:{MUTED}; font-size:12.5px; }}

      /* buttons */
      .stButton>button {{ border-radius:11px; border:1px solid {LINE};
        background:{SURFACE}; color:{TEXT}; font-weight:600; padding:.5rem 1rem; }}
      .stButton>button:hover {{ border-color:{CYAN}; color:{CYAN}; }}
      div[data-testid="stTabs"] button {{ font-weight:600; }}

      /* bar */
      .bar-wrap {{ background:{SURFACE2}; border-radius:8px; height:10px; overflow:hidden;
        border:1px solid {LINE}; }}
      .bar {{ height:100%; border-radius:8px; }}
      .small {{ font-size:12px; color:{MUTED}; }}
      hr {{ border-color:{LINE}; }}
    </style>"""

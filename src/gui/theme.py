"""
Theme Tokens
------------
Single source of truth for all visual constants in the GUI.
Deep blue-violet aesthetic modeled after Linear / Raycast desktop-utility
design language (surface-ladder depth, ONE accent, hairline borders,
dot+text status). Ported 1:1 from ``prototype/design.html`` DESIGN TOKENS;
alpha values are pre-blended into opaque hexes because CTk widget colors
(fg/border/hover/text) accept no rgba.

No hardcoded hex colors should appear outside this module.
"""


def _blend(base_hex: str, overlay_hex: str, overlay_ratio: float) -> str:
    """Opaque equivalent of laying ``overlay`` at ``ratio`` alpha over ``base``."""
    b = [int(base_hex[i:i + 2], 16) for i in (1, 3, 5)]
    o = [int(overlay_hex[i:i + 2], 16) for i in (1, 3, 5)]
    m = [round(b[i] + (o[i] - b[i]) * overlay_ratio) for i in range(3)]
    return "#{:02x}{:02x}{:02x}".format(*m)


class Theme:
    # Surfaces (4-step ladder: sidebar deepest -> content -> cards -> raised)
    BG_DEEP     = "#0a0d1e"   # sidebar / deepest surface  (prototype bg-deep)
    BG_MAIN     = "#0e1228"   # main content area          (bg-main)
    BG_ELEVATED = "#151a36"   # cards, panels              (bg-card)
    BG_RAISED   = "#1c2244"   # hover states, input fills  (bg-raised)
    BG_INSET    = "#0b0f22"   # log/terminal panels        (bg-inset)

    # Borders (1px hairlines, white @ 7% / 14% over BG_MAIN, pre-blended)
    BORDER       = "#1f2337"  # subtle borders on BG_MAIN
    BORDER_LIGHT = "#303346"  # emphasized dividers

    # Text (3 tiers, prototype eef1fa / a3abc8 / 626d92)
    TEXT_PRIMARY   = "#eef1fa"  # headings, active rows
    TEXT_SECONDARY = "#a3abc8"  # descriptions, metadata
    TEXT_MUTED     = "#626d92"  # disabled, placeholders

    # Accent (ONE color: primary CTA + active nav indicator only)
    ACCENT       = "#7c6cf6"  # prototype accent
    ACCENT_HOVER = "#8f7ffa"  # hover lift
    ACCENT_DARK  = "#5b4de0"  # pressed / gradient end (#6366f1 equivalent)
    ACCENT_SOFT  = "#191c3a"  # active-row tint (14% accent over BG_MAIN, opaque)

    # Semantic status (dot + text pairs, never color alone)
    SUCCESS  = "#34d399"  # emerald — healthy/active/completed
    WARNING  = "#fbbf24"  # amber — needs attention (ask gate)
    ERROR    = "#fb7185"  # rose — errors / hold gate / destructive
    ERROR_WASH = _blend(BG_RAISED, "#fb7185", 0.22)  # rose-tinted ghost hover
    INFO     = "#38bdf8"  # sky — informational
    NEUTRAL  = "#94a3b8"  # slate — inactive/stopped

    # Soft washes (12% semantic color over BG_ELEVATED, for chips/status pills)
    SUCCESS_SOFT = _blend(BG_ELEVATED, SUCCESS, 0.12)
    WARNING_SOFT = _blend(BG_ELEVATED, WARNING, 0.12)
    ERROR_SOFT   = _blend(BG_ELEVATED, ERROR, 0.12)
    INFO_SOFT    = _blend(BG_ELEVATED, INFO, 0.12)

    # Category colors (config keys are title-case; "Others" is the fallback)
    CAT_IMAGES    = "#38bdf8"  # sky
    CAT_PDFS      = "#fb923c"  # orange
    CAT_DOCUMENTS = "#8b7cf8"  # violet
    CAT_SETUPS    = "#60a5fa"  # blue
    CAT_SHEETS    = "#2dd4bf"  # teal
    CAT_VIDEOS    = "#fb7185"  # rose
    CAT_ARCHIVES  = "#fbbf24"  # amber
    CAT_AUDIO     = "#34d399"  # emerald
    CAT_OTHERS    = "#94a3b8"  # slate

    _CATEGORY_COLORS = {
        "images": CAT_IMAGES,
        "pdfs": CAT_PDFS,
        "documents": CAT_DOCUMENTS,
        "setups": CAT_SETUPS,
        "sheets": CAT_SHEETS,
        "videos": CAT_VIDEOS,
        "archives": CAT_ARCHIVES,
        "audio": CAT_AUDIO,
        "others": CAT_OTHERS,
    }

    @classmethod
    def category_color(cls, category: str) -> str:
        """Color for a category name (case-insensitive, falls back to Others)."""
        return cls._CATEGORY_COLORS.get((category or "").strip().lower(), cls.CAT_OTHERS)

    # Sizing (4px grid; radii 8 / 12 / 16 / 999 from prototype)
    RADIUS_SM  = 8
    RADIUS_MD  = 12
    RADIUS_LG  = 16
    RADIUS_PILL = 999
    ROW_H      = 40
    BTN_H      = 36
    INPUT_H    = 32
    PAD_LG     = 16
    PAD_MD     = 12
    PAD_SM     = 8

    # Fonts (system sans + system mono; prototype used Inter/Space
    # Grotesk/JetBrains Mono, but those are not guaranteed on the target
    # machine, so family stays generic — weights/sizes carry the hierarchy)
    FONT_FAMILY     = "sans-serif"
    FONT_MONO       = "monospace"
    FONT_H1_SIZE    = 24
    FONT_H2_SIZE    = 16
    FONT_BODY_SIZE  = 14
    FONT_SMALL_SIZE = 12

    # Motion (informational only — CTk has no tween API; animated views
    # in the prototype use micro 150ms / std 250ms / view 200ms)
    MOTION_MICRO_MS = 150
    MOTION_STD_MS   = 250
    MOTION_VIEW_MS  = 200
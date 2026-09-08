"""
Theme Tokens
------------
Single source of truth for all visual constants in the GUI.
Dark Slate + Indigo aesthetic, modeled after Linear / Raycast
desktop-utility design language (surface-ladder depth, one accent,
hairline borders, dot+text status).

No hardcoded hex colors should appear outside this module.
"""
class Theme:
    # Surfaces (3-step ladder: sidebar darkest -> content -> elevated cards lightest)
    BG_DEEP     = "#0b1120"   # sidebar / deepest surface
    BG_MAIN     = "#0f172a"   # main content area (Slate-900)
    BG_ELEVATED = "#1e293b"   # cards, panels (Slate-800)
    BG_RAISED   = "#24344d"   # hover states, input fills

    # Borders (1px hairlines, slightly lighter than surface)
    BORDER       = "#1e293b"  # subtle borders on BG_MAIN
    BORDER_LIGHT = "#334155"  # emphasized dividers (Slate-700)

    # Text (3 tiers)
    TEXT_PRIMARY   = "#e2e8f0"  # headings, active rows (Slate-200)
    TEXT_SECONDARY = "#94a3b8"  # descriptions, metadata (Slate-400)
    TEXT_MUTED     = "#64748b"  # disabled, placeholders (Slate-500)

    # Accent (ONE color, used sparingly: primary CTA + active nav indicator only)
    ACCENT        = "#6366f1"  # Indigo-500
    ACCENT_HOVER  = "#818cf8"  # Indigo-400
    ACCENT_DARK   = "#4f46e5"  # Indigo-600
    ACCENT_SOFT   = "#2a2d4a"  # selected-row tint (opaque indigo wash, CTk has no rgba)

    # Semantic status (dot + text pairs, never color alone)
    SUCCESS  = "#34d399"  # emerald — healthy/active/completed
    WARNING  = "#fbbf24"  # amber — attention needed
    ERROR    = "#fb7185"  # rose — errors/destructive
    ERROR_WASH = "#3b2329"  # rose-tinted hover for destructive ghost buttons
    INFO     = "#60a5fa"  # blue — informational
    NEUTRAL  = "#94a3b8"  # slate — inactive/stopped

    # Sizing
    RADIUS_SM  = 6
    RADIUS_MD  = 8
    RADIUS_LG  = 12
    RADIUS_PILL = 999
    ROW_H      = 40
    BTN_H      = 36
    INPUT_H    = 32
    PAD_LG     = 16
    PAD_MD     = 12
    PAD_SM     = 8

    # Fonts (monospace for logs; system sans otherwise)
    FONT_FAMILY     = "sans-serif"
    FONT_MONO       = "monospace"
    FONT_H1_SIZE    = 22
    FONT_H2_SIZE    = 16
    FONT_BODY_SIZE  = 14
    FONT_SMALL_SIZE = 12
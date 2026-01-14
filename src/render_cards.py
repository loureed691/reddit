"""Card rendering module with font caching and optimized text layout.

Renders title and comment cards as PNG images with:
- LRU caching for font loading to avoid repeated I/O
- Optimized text wrapping algorithm
- Pre-calculated dimensions to avoid image recreation
- Rounded corners and visual polish
"""
from __future__ import annotations
import math
import os
import textwrap
from dataclasses import dataclass
from typing import List, Tuple, Optional

from PIL import Image, ImageDraw, ImageFont

from functools import lru_cache

@dataclass
class CardTheme:
    card_w: int = 900
    padding: int = 48
    radius: int = 32
    bg: Tuple[int,int,int,int] = (18, 18, 22, 235)
    border: Tuple[int,int,int,int] = (255, 255, 255, 24)
    text: Tuple[int,int,int,int] = (245, 245, 245, 255)
    muted: Tuple[int,int,int,int] = (180, 180, 190, 220)
    accent: Tuple[int,int,int,int] = (120, 200, 255, 255)

@lru_cache(maxsize=32)
def _load_font(size: int, prefer: Optional[str]=None) -> ImageFont.FreeTypeFont:
    """Load font with caching to avoid repeated file I/O.
    
    Best effort: use bundled or system. If not found, fallback default.
    """
    # Best effort: use bundled or system. If not found, fallback default.
    candidates = []
    if prefer:
        candidates.append(prefer)
    # common fonts
    candidates += [
        "assets/fonts/Inter-Regular.ttf",
        "assets/fonts/Roboto-Regular.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    for p in candidates:
        try:
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()

def _rounded_rectangle(draw: ImageDraw.ImageDraw, xy, radius, fill, outline=None, width=1):
    # Pillow >= 9 supports rounded_rectangle
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)

def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_w: int) -> List[str]:
    """Wrap text to fit within max width. Optimized version with early break."""
    words = (text or "").split()
    if not words:
        return []
    
    lines: List[str] = []
    cur = ""
    
    for w in words:
        # Test with single word first to handle long words
        single_bbox = draw.textbbox((0,0), w, font=font)
        if (single_bbox[2] - single_bbox[0]) > max_w:
            # Word itself is too long, add it anyway and continue
            if cur:
                lines.append(cur)
            lines.append(w)
            cur = ""
            continue
            
        test = (cur + " " + w).strip()
        bbox = draw.textbbox((0,0), test, font=font)
        if (bbox[2] - bbox[0]) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines

def render_title_card(title: str, subtitle: str="") -> Image.Image:
    """Render a title card with gradient accent bar.
    
    Optimized to calculate exact dimensions first to avoid recreation.
    """
    theme = CardTheme()
    W = theme.card_w
    base_h = 520

    # Pre-create draw context for measurement
    temp_img = Image.new("RGBA", (W, base_h), (0,0,0,0))
    draw = ImageDraw.Draw(temp_img)

    font_title = _load_font(50)
    font_sub = _load_font(28)

    max_text_w = W - 2*theme.padding
    title_lines = _wrap_text(draw, title.strip(), font_title, max_text_w)
    subtitle_lines = _wrap_text(draw, subtitle.strip(), font_sub, max_text_w) if subtitle else []

    # estimate height
    line_h_title = 60
    line_h_sub = 36
    content_h = theme.padding + len(title_lines)*line_h_title + (24 if subtitle_lines else 0) + len(subtitle_lines)*line_h_sub + theme.padding
    H = max(base_h, content_h)

    # Create final image with correct size
    img = Image.new("RGBA", (W, H), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    _rounded_rectangle(draw, (0,0,W,H), theme.radius, fill=theme.bg, outline=theme.border, width=2)

    # little accent bar
    draw.rounded_rectangle((theme.padding, theme.padding, theme.padding+10, H-theme.padding), radius=6, fill=theme.accent)

    x = theme.padding + 24
    y = theme.padding
    for line in title_lines[:10]:
        draw.text((x,y), line, font=font_title, fill=theme.text)
        y += line_h_title

    if subtitle_lines:
        y += 10
        for line in subtitle_lines[:6]:
            draw.text((x,y), line, font=font_sub, fill=theme.muted)
            y += line_h_sub

    return img

def render_comment_card(author: str, body: str, score: int=0) -> Image.Image:
    """Render a comment card with author, body text, and score.
    
    Optimized to calculate exact dimensions first to avoid recreation.
    """
    theme = CardTheme()
    W = theme.card_w
    base_h = 720

    # Pre-create draw context for measurement
    temp_img = Image.new("RGBA", (W, base_h), (0,0,0,0))
    draw = ImageDraw.Draw(temp_img)

    font_author = _load_font(30)
    font_body = _load_font(32)
    font_meta = _load_font(24)

    max_text_w = W - 2*theme.padding
    body_lines = _wrap_text(draw, body.strip(), font_body, max_text_w)

    line_h = 42
    header_h = 110
    content_h = theme.padding + header_h + len(body_lines)*line_h + theme.padding
    H = max(base_h, content_h)

    # Create final image with correct size
    img = Image.new("RGBA", (W, H), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    _rounded_rectangle(draw, (0,0,W,H), theme.radius, fill=theme.bg, outline=theme.border, width=2)

    # author row
    x = theme.padding
    y = theme.padding
    draw.text((x,y), author, font=font_author, fill=theme.text)
    meta = f"score {score}"
    bbox = draw.textbbox((0,0), meta, font=font_meta)
    draw.text((W-theme.padding-(bbox[2]-bbox[0]), y+6), meta, font=font_meta, fill=theme.muted)

    # divider
    y += 54
    draw.line((theme.padding, y, W-theme.padding, y), fill=theme.border, width=2)
    y += 24

    # body
    for line in body_lines[:40]:
        draw.text((x,y), line, font=font_body, fill=theme.text)
        y += line_h

    return img

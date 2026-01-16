"""Card rendering module with font caching and optimized text layout.

Renders title and comment cards as PNG images with:
- LRU caching for font loading to avoid repeated I/O
- Optimized text wrapping algorithm
- Pre-calculated dimensions to avoid image recreation
- Rounded corners and visual polish
- Viral emoji enhancement for better engagement (English only)
"""
from __future__ import annotations
import math
import os
import textwrap
import re
from dataclasses import dataclass
from typing import List, Tuple, Optional

from PIL import Image, ImageDraw, ImageFont

from functools import lru_cache

# Pre-compile emoji patterns for performance
_EMOJI_PATTERNS = [
    # Questions and curiosity (high engagement)
    (re.compile(r'\b(what|why|how|when|who|where)\b', re.IGNORECASE), '🤔'),
    (re.compile(r'\b(secret|hidden|mystery|unknown)\b', re.IGNORECASE), '🔍'),
    
    # Emotional content (viral triggers)
    (re.compile(r'\b(scar(y|iest|ed)|creepy|horror|terrify(ing)?|nightmare)\b', re.IGNORECASE), '😱'),
    (re.compile(r'\b(love|heart|romantic|relationship)\b', re.IGNORECASE), '❤️'),
    (re.compile(r'\b(funny|hilarious|laugh|joke|lol)\b', re.IGNORECASE), '😂'),
    (re.compile(r'\b(angry|mad|furious|rage)\b', re.IGNORECASE), '😠'),
    (re.compile(r'\b(sad|depressing|cry|tear)\b', re.IGNORECASE), '😢'),
    (re.compile(r'\b(surprise|shocked|wow|amazing)\b', re.IGNORECASE), '😲'),
    
    # Success and achievement
    (re.compile(r'\b(win|won|success(ful)?|achieve(ment)?|victory|best)\b', re.IGNORECASE), '🏆'),
    (re.compile(r'\b(money|rich|wealth|dollar|pay)\b', re.IGNORECASE), '💰'),
    
    # Warning and danger
    (re.compile(r'\b(danger|warning|alert|careful|risk)\b', re.IGNORECASE), '⚠️'),
    (re.compile(r'\b(wrong|mistake|fail|error|bad)\b', re.IGNORECASE), '❌'),
    (re.compile(r'\b(right|correct|good|great)\b', re.IGNORECASE), '✅'),
    
    # Technology and gaming
    (re.compile(r'\b(game|gaming|play|video game)\b', re.IGNORECASE), '🎮'),
    (re.compile(r'\b(tech|computer|phone|app)\b', re.IGNORECASE), '💻'),
    
    # Food and lifestyle
    (re.compile(r'\b(food|eat|restaurant|meal)\b', re.IGNORECASE), '🍔'),
    (re.compile(r'\b(coffee|drink|beverage)\b', re.IGNORECASE), '☕'),
    
    # Time and urgency
    (re.compile(r'\b(now|today|urgent|breaking|new)\b', re.IGNORECASE), '🔥'),
    (re.compile(r'\b(night|dark|midnight)\b', re.IGNORECASE), '🌙'),
    
    # People and social
    (re.compile(r'\b(people|person|human|someone)\b', re.IGNORECASE), '👥'),
    (re.compile(r'\b(karen|entitled|rude)\b', re.IGNORECASE), '😤'),
    
    # Places
    (re.compile(r'\b(home|house|apartment)\b', re.IGNORECASE), '🏠'),
    (re.compile(r'\b(work|job|office|boss)\b', re.IGNORECASE), '💼'),
    (re.compile(r'\b(school|college|university|class)\b', re.IGNORECASE), '🎓'),
    
    # Stories and experiences
    (re.compile(r'\b(story|time|experience|happened)\b', re.IGNORECASE), '📖'),
    (re.compile(r'\b(tip|hack|trick|advice)\b', re.IGNORECASE), '💡'),
]

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

def _add_viral_emoji(title: str) -> str:
    """Add relevant emoji to title for viral engagement (English only).
    
    Uses keyword matching to add contextually appropriate emojis.
    Only works with English-language titles.
    
    Note: Emoji is added at render time and becomes part of the displayed title.
    This may affect text wrapping and layout calculations.
    """
    # Check for existing emojis first (optimization - avoid pattern matching if not needed)
    has_emoji = any(
        0x1F300 <= ord(char) <= 0x1F9FF or  # Main emoji range (includes emoticons 0x1F600-0x1F64F)
        0x2600 <= ord(char) <= 0x26FF or    # Symbols (includes ❤️)
        0x2700 <= ord(char) <= 0x27BF or    # Misc symbols
        0x1F100 <= ord(char) <= 0x1F1FF or  # Enclosed Alphanumeric Supplement
        0x1F200 <= ord(char) <= 0x1F2FF or  # Enclosed Ideographic Supplement
        0x1FA70 <= ord(char) <= 0x1FAFF     # Symbols & Pictographs Extended-A
        for char in title
    )
    
    if has_emoji:
        return title
    
    # Find the first matching pattern using pre-compiled patterns
    for pattern, emoji in _EMOJI_PATTERNS:
        if pattern.search(title):
            return f"{emoji} {title}"
    
    return title

def render_title_card(title: str, subtitle: str="") -> Image.Image:
    """Render a title card with gradient accent bar.
    
    Optimized to calculate exact dimensions first to avoid recreation.
    Includes viral emoji enhancement for better engagement.
    """
    # Add emoji for viral engagement
    title = _add_viral_emoji(title)
    
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
        # Add subtle text shadow for better mobile readability
        draw.text((x+2, y+2), line, font=font_title, fill=(0, 0, 0, 180))
        draw.text((x, y), line, font=font_title, fill=theme.text)
        y += line_h_title

    if subtitle_lines:
        y += 10
        for line in subtitle_lines[:6]:
            # Add subtle shadow to subtitle too
            draw.text((x+1, y+1), line, font=font_sub, fill=(0, 0, 0, 120))
            draw.text((x, y), line, font=font_sub, fill=theme.muted)
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

    # author row with shadow
    x = theme.padding
    y = theme.padding
    draw.text((x+2, y+2), author, font=font_author, fill=(0, 0, 0, 180))
    draw.text((x, y), author, font=font_author, fill=theme.text)
    meta = f"score {score}"
    bbox = draw.textbbox((0,0), meta, font=font_meta)
    meta_x = W-theme.padding-(bbox[2]-bbox[0])
    draw.text((meta_x+1, y+7), meta, font=font_meta, fill=(0, 0, 0, 120))
    draw.text((meta_x, y+6), meta, font=font_meta, fill=theme.muted)

    # divider
    y += 54
    draw.line((theme.padding, y, W-theme.padding, y), fill=theme.border, width=2)
    y += 24

    # body with shadow for better readability
    for line in body_lines[:40]:
        draw.text((x+1, y+1), line, font=font_body, fill=(0, 0, 0, 120))
        draw.text((x, y), line, font=font_body, fill=theme.text)
        y += line_h

    return img

def render_outro_cta_card(bottom_text: str = "More stories coming soon!") -> Image.Image:
    """Render an engaging call-to-action outro card for viral engagement.
    
    Encourages viewers to like, follow, and engage - critical for algorithm performance.
    Optimized for TikTok, YouTube Shorts, and Instagram Reels.
    
    Args:
        bottom_text: Customizable text shown at the bottom of the card
    """
    theme = CardTheme()
    W = theme.card_w
    H = 720
    
    img = Image.new("RGBA", (W, H), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    _rounded_rectangle(draw, (0,0,W,H), theme.radius, fill=theme.bg, outline=theme.border, width=2)
    
    # Large CTA fonts
    font_main = _load_font(48)
    font_sub = _load_font(32)
    
    y = 120
    
    # Main CTA with emojis - improved contrast colors for accessibility
    cta_lines = [
        ("👍 Like", (255, 120, 120, 255)),      # Slightly lighter red for better contrast
        ("🔔 Follow", theme.accent),             # Use theme accent color
        ("💬 Comment", (255, 220, 100, 255)),   # Brighter yellow for better contrast
    ]
    
    line_height = 120
    for text, color in cta_lines:
        # Center the text
        bbox = draw.textbbox((0, 0), text, font=font_main)
        text_w = bbox[2] - bbox[0]
        x = (W - text_w) // 2
        
        # Add shadow
        draw.text((x+3, y+3), text, font=font_main, fill=(0, 0, 0, 180))
        draw.text((x, y), text, font=font_main, fill=color)
        y += line_height
    
    # Bottom text (customizable)
    y = H - 100
    bbox = draw.textbbox((0, 0), bottom_text, font=font_sub)
    text_w = bbox[2] - bbox[0]
    x = (W - text_w) // 2
    draw.text((x+2, y+2), bottom_text, font=font_sub, fill=(0, 0, 0, 120))
    draw.text((x, y), bottom_text, font=font_sub, fill=theme.muted)
    
    return img

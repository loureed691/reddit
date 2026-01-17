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
# Using Unicode symbols that render reliably across all fonts
_EMOJI_PATTERNS = [
    # Questions and curiosity (high engagement)
    (re.compile(r'\b(what|why|how|when|who|where)\b', re.IGNORECASE), '🤔'),
    (re.compile(r'\b(secret|hidden|mystery|unknown)\b', re.IGNORECASE), '🔍'),
    
    # Emotional content (viral triggers)
    (re.compile(r'\b(scar(y|iest|ed)|creepy|horror|terrify(ing)?|nightmare)\b', re.IGNORECASE), '😱'),
    (re.compile(r'\b(love|heart|romantic|relationship)\b', re.IGNORECASE), '❤'),
    (re.compile(r'\b(funny|hilarious|laugh|joke|lol)\b', re.IGNORECASE), '😂'),
    (re.compile(r'\b(angry|mad|furious|rage)\b', re.IGNORECASE), '😠'),
    (re.compile(r'\b(sad|depressing|cry|tear)\b', re.IGNORECASE), '😢'),
    (re.compile(r'\b(surprise|shocked|wow|amazing)\b', re.IGNORECASE), '😲'),
    
    # Success and achievement
    (re.compile(r'\b(win|won|success(ful)?|achieve(ment)?|victory|best)\b', re.IGNORECASE), '🏆'),
    (re.compile(r'\b(money|rich|wealth|dollar|pay)\b', re.IGNORECASE), '💰'),
    
    # Warning and danger
    (re.compile(r'\b(danger|warning|alert|careful|risk)\b', re.IGNORECASE), '⚠'),
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
    """Theme configuration for card rendering with glassmorphism design.
    
    Dimensions are optimized for vertical video (1080x1920):
    - card_w: 1050px - increased for better readability (fills ~97% of screen width)
    - padding: 70px - increased for better spacing and readability
    - radius: 40px creates modern rounded corners without being excessive
    
    Colors chosen for:
    - High contrast on colorful backgrounds (dark bg, white text)
    - Premium glassmorphism aesthetic (semi-transparent with gradient borders)
    - Mobile readability (sufficient contrast ratios)
    """
    card_w: int = 1050  # Card width increased for better readability
    padding: int = 70   # Internal padding increased for better spacing
    radius: int = 40    # Corner radius for modern aesthetic
    # Text indentation values for visual hierarchy
    title_text_indent: int = 32  # Indent for title text (base offset from accent bar)
    comment_body_indent: int = 24  # Indent for comment body text
    # Modern glassmorphism - semi-transparent dark with blur effect simulation
    bg: Tuple[int,int,int,int] = (15, 15, 20, 245)  # ~96% opacity for depth
    # Gradient border with higher opacity for premium look
    border: Tuple[int,int,int,int] = (255, 255, 255, 60)
    border_gradient_start: Tuple[int,int,int,int] = (138, 180, 248, 180)  # Soft blue
    border_gradient_end: Tuple[int,int,int,int] = (195, 140, 255, 180)    # Soft purple
    # Enhanced text colors for better readability
    text: Tuple[int,int,int,int] = (255, 255, 255, 255)
    muted: Tuple[int,int,int,int] = (200, 200, 210, 240)
    # Multiple accent colors for variety
    accent_blue: Tuple[int,int,int,int] = (100, 180, 255, 255)
    accent_purple: Tuple[int,int,int,int] = (180, 100, 255, 255)
    accent_gradient: Tuple[int,int,int,int] = (138, 180, 248, 255)
    # Shadow color for depth
    shadow: Tuple[int,int,int,int] = (0, 0, 0, 80)  # ~31% opacity

@lru_cache(maxsize=32)
def _load_font(size: int, prefer: Optional[str]=None) -> ImageFont.FreeTypeFont:
    """Load font with caching to avoid repeated file I/O.
    
    Best effort: use bundled or system. If not found, fallback default.
    Prioritizes fonts with better emoji/Unicode support.
    """
    candidates = []
    if prefer:
        candidates.append(prefer)
    # Prioritize fonts with better Unicode/emoji support
    candidates += [
        "assets/fonts/Inter-Regular.ttf",
        "assets/fonts/Roboto-Regular.ttf",
        # Symbola has excellent emoji support (monochrome, works with Pillow)
        # Check multiple possible locations for Symbola
        "/usr/share/fonts/truetype/ancient-scripts/Symbola_hint.ttf",
        "/usr/share/fonts/truetype/Symbola.ttf",
        "/usr/share/fonts/TTF/Symbola.ttf",
        # Windows emoji fonts
        os.path.join("C:", "Windows", "Fonts", "seguiemj.ttf"),  # Segoe UI Emoji
        os.path.join("C:", "Windows", "Fonts", "segoeui.ttf"),   # Segoe UI (has emoji fallback)
        os.path.join("C:", "Windows", "Fonts", "arial.ttf"),
        # Linux fonts
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        # macOS fonts (TTF files only - TTC format may not be fully supported by Pillow)
        "/Library/Fonts/Arial Unicode.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    for p in candidates:
        try:
            if os.path.exists(p):
                font = ImageFont.truetype(p, size)
                # Candidates are ordered by Unicode/emoji quality; return the first successfully loaded font
                return font
        except Exception:
            pass
    return ImageFont.load_default()

def _rounded_rectangle(draw: ImageDraw.ImageDraw, xy, radius, fill, outline=None, width=1):
    # Pillow >= 9 supports rounded_rectangle
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)

def _draw_gradient_border(img: Image.Image, xy: Tuple[int, int, int, int], radius: int, color1: Tuple[int,int,int,int], color2: Tuple[int,int,int,int], width: int=3):
    """Draw a gradient border on an image for premium look."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    # Draw multiple borders with gradient colors
    x1, y1, x2, y2 = xy
    steps = max(1, width)
    
    for i in range(steps):
        t = i / max(1, steps - 1) if steps > 1 else 0
        r = int(color1[0] * (1-t) + color2[0] * t)
        g = int(color1[1] * (1-t) + color2[1] * t)
        b = int(color1[2] * (1-t) + color2[2] * t)
        a = int(color1[3] * (1-t) + color2[3] * t)
        
        offset = i
        draw.rounded_rectangle(
            (x1 + offset, y1 + offset, x2 - offset, y2 - offset),
            radius=max(1, radius - offset),
            outline=(r, g, b, a),
            width=1
        )
    
    img.paste(overlay, (0, 0), overlay)

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
    """Render a modern title card with glassmorphism effect and gradient accents.
    
    Optimized to calculate exact dimensions first to avoid recreation.
    Includes viral emoji enhancement for better engagement.
    """
    # Add emoji for viral engagement
    title = _add_viral_emoji(title)
    
    theme = CardTheme()
    W = theme.card_w
    base_h = 540

    # Pre-create draw context for measurement
    temp_img = Image.new("RGBA", (W, base_h), (0,0,0,0))
    draw = ImageDraw.Draw(temp_img)

    # Use larger fonts for better readability - increased to 72/44 for improved visibility
    font_title = _load_font(72)
    font_sub = _load_font(44)

    # Account for text indentation in wrapping calculation
    max_text_w = W - 2*theme.padding - theme.title_text_indent - 8  # 8px extra for accent bar glow
    title_lines = _wrap_text(draw, title.strip(), font_title, max_text_w)
    subtitle_lines = _wrap_text(draw, subtitle.strip(), font_sub, max_text_w) if subtitle else []

    # Estimate height with better spacing - adjusted for larger fonts
    line_h_title = 88  # Increased for 72px font
    line_h_sub = 54    # Increased for 44px font
    content_h = theme.padding + len(title_lines)*line_h_title + (32 if subtitle_lines else 0) + len(subtitle_lines)*line_h_sub + theme.padding
    H = max(base_h, content_h)

    # Create final image with shadow layer for depth
    img = Image.new("RGBA", (W, H), (0,0,0,0))
    
    # Draw subtle shadow for depth
    shadow_img = Image.new("RGBA", (W, H), (0,0,0,0))
    shadow_draw = ImageDraw.Draw(shadow_img)
    shadow_offset = 6
    _rounded_rectangle(shadow_draw, (shadow_offset, shadow_offset, W - 1, H - 1), 
                      theme.radius, fill=theme.shadow)
    img.paste(shadow_img, (0, 0), shadow_img)
    
    # Main card background
    draw = ImageDraw.Draw(img)
    _rounded_rectangle(draw, (0, 0, W, H), theme.radius, fill=theme.bg)
    
    # Add gradient border for premium look
    _draw_gradient_border(img, (0, 0, W, H), theme.radius, 
                         theme.border_gradient_start, theme.border_gradient_end, width=3)

    # Enhanced gradient accent bar with glow (optimized and bounds-safe)
    accent_x = theme.padding - 4
    accent_w = 12
    accent_y1 = theme.padding
    accent_y2 = H - theme.padding
    
    # Draw glow behind accent bar - reduced iterations for performance
    # Uses 4 layers with exponentially increasing spread
    glow_layers = 4
    for i in range(glow_layers, 0, -1):
        alpha = int(50 * (i / glow_layers))
        glow_color = (*theme.accent_blue[:3], alpha)
        draw.rounded_rectangle(
            (max(0, accent_x - i*2), accent_y1, accent_x + accent_w + i*2, accent_y2),
            radius=8, fill=glow_color
        )
    
    # Main accent bar with gradient effect
    draw.rounded_rectangle((accent_x, accent_y1, accent_x + accent_w, accent_y2), 
                          radius=8, fill=theme.accent_gradient)

    # Draw text with enhanced positioning
    x = theme.padding + theme.title_text_indent
    y = theme.padding
    
    for line in title_lines[:10]:
        # Add subtle text shadow for better mobile readability
        draw.text((x+2, y+2), line, font=font_title, fill=(0, 0, 0, 180))
        draw.text((x, y), line, font=font_title, fill=theme.text)
        y += line_h_title

    if subtitle_lines:
        y += 16
        for line in subtitle_lines[:6]:
            # Add subtle shadow to subtitle too
            draw.text((x+1, y+1), line, font=font_sub, fill=(0, 0, 0, 120))
            draw.text((x, y), line, font=font_sub, fill=theme.muted)
            y += line_h_sub

    return img

def render_comment_card(author: str, body: str, score: int=0) -> Image.Image:
    """Render a modern comment card with enhanced visual design.
    
    Enhanced design features:
    - Glassmorphism background with gradient border
    - Better typography and spacing
    - Visual icons and separators
    - Score badge with gradient background
    - Author highlighting
    """
    theme = CardTheme()
    W = theme.card_w
    base_h = 740

    # Pre-create draw context for measurement
    temp_img = Image.new("RGBA", (W, base_h), (0,0,0,0))
    draw = ImageDraw.Draw(temp_img)

    # Increased font sizes for better readability - increased to 46/48/34 for improved visibility
    font_author = _load_font(46)
    font_body = _load_font(48)
    font_meta = _load_font(34)

    # Account for indent in body text wrapping calculation
    max_text_w = W - 2*theme.padding - theme.comment_body_indent
    body_lines = _wrap_text(draw, body.strip(), font_body, max_text_w)

    line_h = 58  # Increased for 48px font
    header_h = 130
    content_h = theme.padding + header_h + len(body_lines)*line_h + theme.padding
    H = max(base_h, content_h)

    # Create final image with shadow for depth
    img = Image.new("RGBA", (W, H), (0,0,0,0))
    
    # Draw subtle shadow
    shadow_img = Image.new("RGBA", (W, H), (0,0,0,0))
    shadow_draw = ImageDraw.Draw(shadow_img)
    shadow_offset = 6
    _rounded_rectangle(shadow_draw, (shadow_offset, shadow_offset, W - 1, H - 1), 
                      theme.radius, fill=theme.shadow)
    img.paste(shadow_img, (0, 0), shadow_img)
    
    # Main card background
    draw = ImageDraw.Draw(img)
    _rounded_rectangle(draw, (0, 0, W, H), theme.radius, fill=theme.bg)
    
    # Add gradient border
    _draw_gradient_border(img, (0, 0, W, H), theme.radius, 
                         theme.border_gradient_start, theme.border_gradient_end, width=3)

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

    # Enhanced divider with gradient (optimized for performance)
    y += 64
    divider_y = y
    # Draw gradient divider with fewer, thicker lines for better performance
    divider_width = max(1, W - 2 * theme.padding)  # Prevent division by zero
    # Use step size to reduce iterations from 808 to ~200
    step = 4
    steps = max(2, divider_width // step)
    for i in range(steps):
        # Normalize position along the gradient [0, 1]
        t = i / (steps - 1) if steps > 1 else 0
        alpha = int(60 * (1 - abs(t - 0.5) * 2))  # Fade at edges
        color = (*theme.border_gradient_start[:3], alpha)
        # Map step index back to an x-coordinate within the gradient span
        x = theme.padding + int(i * divider_width / (steps - 1)) if steps > 1 else theme.padding
        draw.line((x, divider_y, x, divider_y + 2), fill=color, width=step)
    
    y += 28

    # body with shadow for better readability
    # Add indent for visual hierarchy and breathing room
    body_x = theme.padding + theme.comment_body_indent
    for line in body_lines[:40]:
        draw.text((body_x+1, y+1), line, font=font_body, fill=(0, 0, 0, 120))
        draw.text((body_x, y), line, font=font_body, fill=theme.text)
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
    
    # Larger CTA fonts for better readability - increased to 64/44 for improved visibility
    font_main = _load_font(64)
    font_sub = _load_font(44)
    
    y = 120
    
    # Main CTA with emojis - improved contrast colors for accessibility
    cta_lines = [
        ("👍 Like", (255, 120, 120, 255)),      # Slightly lighter red for better contrast
        ("🔔 Follow", theme.accent_blue),        # Use theme accent color
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

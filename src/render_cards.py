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
    """Theme configuration for card rendering with glassmorphism design.
    
    Dimensions are optimized for vertical video (1080x1920):
    - card_w: 920px fits comfortably with margins in 1080px width
    - padding: 56px provides breathing room for content
    - radius: 40px creates modern rounded corners without being excessive
    
    Colors chosen for:
    - High contrast on colorful backgrounds (dark bg, white text)
    - Premium glassmorphism aesthetic (semi-transparent with gradient borders)
    - Mobile readability (sufficient contrast ratios)
    """
    card_w: int = 920  # Card width optimized for 1080px vertical video
    padding: int = 56  # Internal padding for content breathing room
    radius: int = 40   # Corner radius for modern aesthetic
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

# Spacing constants for consistent card sizing
# These provide breathing room around content for better visual presentation
TITLE_EXTRA_SPACING_WITH_SUBTITLE = 40  # Extra spacing when subtitle is present
TITLE_EXTRA_SPACING_NO_SUBTITLE = 20    # Extra spacing when no subtitle
TITLE_BOTTOM_MARGIN = 20                 # Bottom margin for title cards
COMMENT_EXTRA_SPACING = 30               # Extra spacing for comment cards

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

def render_title_card(title: str, subtitle: str="") -> Image.Image:
    """Render a modern title card with glassmorphism effect and gradient accents.
    
    Enhanced design features:
    - Glassmorphism background with gradient border
    - Larger, more prominent text
    - Gradient accent bar with glow effect
    - Better spacing and visual hierarchy
    - Properly sized to fit all text content
    """
    theme = CardTheme()
    W = theme.card_w
    base_h = 540

    # Pre-create draw context for measurement
    temp_img = Image.new("RGBA", (W, base_h), (0,0,0,0))
    draw = ImageDraw.Draw(temp_img)

    # Use larger fonts for better readability
    font_title = _load_font(56)
    font_sub = _load_font(32)

    max_text_w = W - 2*theme.padding - 40  # Extra margin for accent bar
    title_lines = _wrap_text(draw, title.strip(), font_title, max_text_w)
    subtitle_lines = _wrap_text(draw, subtitle.strip(), font_sub, max_text_w) if subtitle else []

    # Calculate height with generous spacing to fit all content
    line_h_title = 68
    line_h_sub = 42
    # Use spacing constants for visual elements (shadow, border, etc.) and breathing room
    extra_spacing = TITLE_EXTRA_SPACING_WITH_SUBTITLE if subtitle_lines else TITLE_EXTRA_SPACING_NO_SUBTITLE
    content_h = theme.padding + len(title_lines)*line_h_title + extra_spacing + len(subtitle_lines)*line_h_sub + theme.padding + TITLE_BOTTOM_MARGIN
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
    x = theme.padding + 32
    y = theme.padding
    
    # Render all title lines (no artificial limit)
    for line in title_lines:
        draw.text((x, y), line, font=font_title, fill=theme.text)
        y += line_h_title

    if subtitle_lines:
        y += 16
        # Render all subtitle lines (no artificial limit)
        for line in subtitle_lines:
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
    - Properly sized to fit all text content
    """
    theme = CardTheme()
    W = theme.card_w
    base_h = 740

    # Pre-create draw context for measurement
    temp_img = Image.new("RGBA", (W, base_h), (0,0,0,0))
    draw = ImageDraw.Draw(temp_img)

    font_author = _load_font(34)
    font_body = _load_font(36)
    font_meta = _load_font(26)

    max_text_w = W - 2*theme.padding
    body_lines = _wrap_text(draw, body.strip(), font_body, max_text_w)

    line_h = 46
    header_h = 120
    # Use spacing constant for visual elements and breathing room
    content_h = theme.padding + header_h + len(body_lines)*line_h + theme.padding + COMMENT_EXTRA_SPACING
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

    # Header section
    x = theme.padding
    y = theme.padding
    
    # Author name with highlight
    author_text = f"u/{author}"
    draw.text((x, y), author_text, font=font_author, fill=theme.accent_blue)
    
    # Score badge with gradient background (optimized)
    meta = f"↑ {score:,}"
    bbox = draw.textbbox((0, 0), meta, font=font_meta)
    badge_w = (bbox[2] - bbox[0]) + 24
    badge_h = (bbox[3] - bbox[1]) + 16
    badge_x = W - theme.padding - badge_w
    badge_y = max(0, y - 4)  # Prevent negative coordinates
    
    # Draw gradient badge background - reduced layers for performance
    badge_color = (*theme.accent_purple[:3], 140)
    draw.rounded_rectangle(
        (badge_x, badge_y, badge_x + badge_w, badge_y + badge_h),
        radius=16,
        fill=badge_color
    )
    
    # Draw score text
    text_x = badge_x + 12
    text_y = badge_y + 8
    draw.text((text_x, text_y), meta, font=font_meta, fill=theme.text)

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

    # Body text with enhanced spacing
    # Render all body lines (no artificial limit)
    for line in body_lines:
        draw.text((x, y), line, font=font_body, fill=theme.text)
        y += line_h

    return img

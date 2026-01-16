# Reddit Video Factory (standalone, Jan 2026 friendly)

This is the **whole factory**: fetch a Reddit thread, pick comments, generate title/comment images, generate TTS audio, generate (or use) a background video, then render a final vertical MP4.

No magic, no hidden utils folder. Just files.

## Features

- **Fully Automated Mode**: Automatically search for suitable Reddit posts and produce videos
- **Duplicate Prevention**: Tracks produced videos to avoid creating duplicates
- **Configurable Video Lengths**: Create short (1-2 minutes) or long (60 minutes) videos
- **Manual or Auto Mode**: Run with specific URLs or let it find posts automatically
- **Word-by-Word Text Animation**: Text appears word by word synchronized with TTS audio for enhanced engagement

## What you need installed

- **Python 3.10+** (3.11/3.12 also fine)
- **ffmpeg** on PATH
  - Verify: `ffmpeg -version`
  - Verify encoder: `ffmpeg -hide_banner -encoders | grep -i libx264` (Linux/macOS)  
    or `ffmpeg -hide_banner -encoders | findstr /i libx264` (Windows)

## Install

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

## Quick start

### Automated Mode (Recommended)

Let the tool automatically find and produce videos from suitable Reddit posts:

```bash
# Run with default settings (short 1-2 minute videos)
python run.py --auto

# Run with long 60-minute videos
python run.py --auto --duration-mode long
```

The automation will:
1. Search configured subreddits for posts meeting criteria (score, comments)
2. Skip posts that have already been produced
3. Create a video from the first suitable post found
4. Track the video to prevent duplicates

### Manual Mode

Render a video from a specific Reddit URL:

```bash
python run.py --url "https://www.reddit.com/r/AskReddit/comments/THREAD_ID/some_title/" --comments 12
```

Output:
- `results/<subreddit>/<safe_title>.mp4`

Temp files (for debugging):
- `assets/temp/<thread_id>/...`

## Configuration

Edit `config.json` to customize:

### Video Duration Settings

```json
"video_duration": {
  "mode": "short",                    // "short" or "long"
  "target_duration_seconds": 90,      // Target for short mode (1-2 min)
  "long_duration_seconds": 3600       // Target for long mode (60 min)
}
```

### Automation Settings

```json
"automation": {
  "enabled": true,                    // Enable auto mode by default
  "subreddits": [                     // Subreddits to search
    "AskReddit", 
    "todayilearned", 
    "explainlikeimfive"
  ],
  "sort_by": "hot",                   // "hot", "top", or "new"
  "time_filter": "day",               // For "top": "hour", "day", "week", "month", "year", "all"
  "min_score": 1000,                  // Minimum post score
  "min_comments": 50,                 // Minimum comment count
  "produced_videos_db": "produced_videos.json"  // Tracking database
}
```

### Word-by-Word Animation Settings

```json
"settings": {
  "word_by_word_animation": true     // Enable word-by-word text animation (default: true)
}
```

When enabled, text on Reddit cards appears word by word, synchronized with the TTS audio. This creates a more engaging viewing experience, especially for short-form viral content on TikTok, YouTube Shorts, and Instagram Reels.

**How it works:**
- Uses edge-tts WordBoundary events to capture precise timing for each spoken word
- Generates multiple card images showing progressive text reveal
- Overlays cards at precise timings to match the spoken audio
- Falls back to showing full text immediately if word timings are unavailable (e.g., with pyttsx3)

**Performance note:** Word-by-word animation generates more image files and overlay operations. For videos with many long comments, you may want to disable this feature by setting `"word_by_word_animation": false` in your config.

## Options

- **Automated mode**:
  - `--auto`: Run in automated mode
  - `--duration-mode short|long`: Override video duration mode
  
- **Manual mode**:
  - `--url <URL>`: Specific Reddit thread URL or ID
  - `--comments 8`: Pick comment count
  
- **Common options**:
  - `--lang en` or `--lang de`: Force language for card text wrapping
  - `--background path/to/background.mp4`: Use your own background video
  - `--keep-temp`: Keep temp folder for debugging
  - `--config path/to/config.json`: Use alternative config file

## How it works (pipeline)

1. **Search** (Auto mode): Find suitable posts from configured subreddits
2. **Fetch**: Get thread JSON from `https://www.reddit.com/comments/<id>.json`
3. **Duration Targeting**: Select comments to fit target duration (90s or 3600s)
4. **Render Cards**: Create PNG images with Pillow
   - With word-by-word animation: Generate multiple progressive frames per card
   - Without animation: Generate single static card per title/comment
5. **Generate TTS MP3**:
   - Default: `edge-tts` (best quality, needs internet)
   - Voice: `en-US-AriaNeural` (optimized for viral content)
   - Rate: `+12%` (1.12x speed for better engagement)
   - Captures word boundary timings when word-by-word animation is enabled
   - Fallback: `pyttsx3` (offline, robotic, no word timings)
6. **Background**:
   - If you pass `--background`, it uses that
   - Else it generates a viral-optimized animated background:
     - **Vibrant gradients** (purple-pink, blue-cyan, orange-red, etc.)
     - **Dynamic motion** with sinusoidal zoom/pan (breathing effect)
     - **3 style options**: gradient (default), radial, or noise
     - Optimized for TikTok, YouTube Shorts, Instagram Reels engagement
7. **Merge**:
   - Concatenate audio clips
   - Overlay cards on background with precise timing
   - Word-by-word mode: Multiple overlays per card synchronized with speech
   - Traditional mode: Single overlay per card for entire audio duration
   - Encode `libx264 + aac` MP4, `yuv420p`, `faststart`
8. **Track** (Auto mode): Mark video as produced to prevent duplicates

## Troubleshooting

### “Missing file …”
Your temp pipeline didn’t generate what the builder expects. Re-run with `--keep-temp` and check `assets/temp/<thread_id>/`.

### “Unknown encoder libx264”
Your ffmpeg is a sad minimal build. Install a real ffmpeg package.

### TTS fails
- `edge-tts` requires internet. If it can’t reach the service, it will fall back to `pyttsx3`.
- On Linux you may need system speech deps for `pyttsx3` (espeak). If you don’t want that, install `edge-tts` and use internet.

## Notes

- Reddit may rate-limit you. This tool sets a user-agent and uses the public JSON endpoint.
- Don’t upload videos you don’t have rights to. Humans and copyright lawyers exist.

### "No suitable posts found"
If running in automated mode:
- Check your automation settings in `config.json`
- Lower `min_score` or `min_comments` thresholds
- Try different subreddits
- Check if all matching posts have already been produced (check `produced_videos.json`)

### Video is too short/long
- For short videos: Adjust `target_duration_seconds` in `config.json` (default 90s = 1.5 min)
- For long videos: Use `--duration-mode long` or set mode to "long" in config
- The tool will select as many comments as fit within the target duration

## Examples

### Create short videos automatically from AskReddit
```bash
python run.py --auto
```

### Create a 60-minute video from trending posts
```bash
python run.py --auto --duration-mode long
```

### Create a specific 2-minute video
```bash
python run.py --url "https://www.reddit.com/r/AskReddit/comments/abc123/..." --duration-mode short
```

### Use custom configuration
```bash
python run.py --auto --config my_custom_config.json
```

## Additional Notes

- Videos are tracked in `produced_videos.json` to prevent duplicates in automated mode.
- Adjust duration targets in `config.json` to fine-tune video lengths.
- The automation will skip posts that have already been produced, preventing waste.

## TTS Viral Optimization

The default TTS settings have been optimized for viral short-form content (TikTok, YouTube Shorts, Instagram Reels) based on 2026 best practices:

- **Voice**: `en-US-AriaNeural` - Modern, conversational voice that resonates with younger audiences
- **Speech Rate**: `+12%` (1.12x speed) - Slightly faster pace keeps attention and matches short-form content expectations
- **Why these settings?**: Analysis of viral Reddit story videos shows that slightly faster, more conversational voices perform significantly better in terms of views, retention, and engagement

You can customize these in `config.json` under the `voice` section. Other recommended viral voices:
- `en-US-EmmaMultilingualNeural` - Warm, natural flow
- `en-US-AndrewMultilingualNeural` - Mature, engaging male voice
- `en-US-BrianMultilingualNeural` - Smooth, clear tone

For maximum virality, keep the speech rate between +10% and +15% - this matches the pacing expectations of modern short-form video audiences while maintaining clarity and naturalness.

## Background Viral Optimization

The background generation has been optimized for maximum engagement on short-form video platforms (TikTok, YouTube Shorts, Instagram Reels):

### Visual Styles

Five state-of-the-art background styles are available, configurable in `config.json`:

1. **Particles (Default - Most Engaging)** - Dynamic particle field with glowing effects
   - Hundreds of animated light particles creating depth and motion
   - Excellent for maximum viewer retention and engagement
   - Perfect for high-energy, viral-optimized content

2. **Waves (NEW - Hypnotic)** - Flowing wave patterns with multiple frequencies
   - Mesmerizing wave animations that create a calming yet engaging effect
   - Great for longer-form content where you want sustained attention
   - Works well with educational or explanatory content

3. **Gradient (Enhanced)** - Smooth diagonal gradients with vibrant colors
   - Sunset Orange-Pink (high energy)
   - Blue-cyan (clean, modern)
   - Purple-pink (trending on TikTok)
   - Teal-green (calming but vibrant)
   - Violet-blue (mysterious, engaging)

4. **Radial** - Center-focused gradients that draw attention to the middle
   - Creates a natural focal point for text overlays
   - Excellent for story-telling content
   - Enhanced with smoother falloff curves

5. **Noise** - Enhanced version of the original noise background
   - Brighter, more vibrant colors than before
   - Good for less distracting backgrounds

### Dynamic Motion

The background features enhanced motion patterns optimized for each style:

**Particles Style:**
- Energetic motion with zoom oscillation (1.0-1.4x range)
- Rapid circular pan with 30px radius
- Creates excitement and energy

**Waves Style:**
- Slower, flowing motion with zoom oscillation (0.97-1.33x range)
- Gentle pan with 25px radius
- Creates a calming, hypnotic effect

**Gradient/Radial Styles:**
- Balanced motion with rotation-like effect (1.01-1.35x range)
- Circular pan with subtle asymmetric motion
- Natural, organic feel

All motion patterns use sinusoidal (non-linear) movement for a "breathing" effect that's proven to retain attention better than linear movement in viral content analysis.

### Configuration

Edit `config.json` to customize:

```json
"background": {
  "style": "particles",  // "particles", "waves", "gradient", "radial", or "noise"
  "auto_generate_background": true,
  "background_audio_volume": 0.12
}
```

**Recommended Styles by Content Type:**
- **Viral/Short-form content:** Use "particles" for maximum engagement
- **Long-form/Educational:** Use "waves" for sustained attention without distraction
- **Story/Narrative:** Use "gradient" or "radial" for focus on content
- **Minimal distraction:** Use "noise" for subtler backgrounds

### Why These Optimizations Work

1. **Enhanced Visual Styles**: Particle and wave backgrounds provide more dynamic, engaging visuals than static gradients
2. **Glassmorphism Cards**: Modern card design with gradient borders and shadows creates premium, professional look
3. **Better Typography**: Larger fonts, improved spacing, and better color contrast ensure readability on mobile
4. **Dynamic Motion**: Style-specific motion patterns keep viewers engaged without being distracting
5. **Platform Optimization**: Designed specifically for vertical video (1080x1920) on TikTok/Shorts/Reels
6. **Visual Hierarchy**: Improved card layouts with icons, badges, and separators guide viewer attention

The particles style is now the default as it provides the best balance of visual interest and engagement for viral short-form content, while waves style is recommended for longer videos where sustained attention is key.

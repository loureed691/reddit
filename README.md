# Reddit Video Factory (standalone, Jan 2026 friendly)

This is the **whole factory**: fetch a Reddit thread, pick comments, generate title/comment images, generate TTS audio, generate (or use) a background video, then render a final vertical MP4.

No magic, no hidden utils folder. Just files.

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

## Quick start (one command)

### Render a video from a Reddit URL

```bash
python run.py --url "https://www.reddit.com/r/AskReddit/comments/THREAD_ID/some_title/" --comments 12
```

Output:
- `results/<subreddit>/<safe_title>.mp4`

Temp files (for debugging):
- `assets/temp/<thread_id>/...`

## Options

- Pick comment count:
  - `--comments 8`
- Force language for card text wrapping:
  - `--lang en` or `--lang de`
- Use your own background video:
  - `--background path/to/background.mp4`
- Disable background audio mixing:
  - set `settings.background.enable_extra_audio` to `false` or volume to `0` in `config.json`
- Keep temp folder:
  - `--keep-temp`

## How it works (pipeline)

1. Fetch thread JSON: `https://www.reddit.com/comments/<id>.json`
2. Extract title + top comments
3. Render PNG "cards" with Pillow (`title.png` + `comment_0.png`…)
4. Generate TTS MP3:
   - Default: `edge-tts` (best quality, needs internet)
   - Fallback: `pyttsx3` (offline, robotic)
5. Background:
   - If you pass `--background`, it uses that
   - Else it generates an abstract moving noise background with ffmpeg
6. Merge:
   - Concatenate audio clips
   - Overlay cards on background in sync with audio duration
   - Encode `libx264 + aac` MP4, `yuv420p`, `faststart`

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

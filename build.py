"""Expose only website assets through Vercel's CDN."""
from pathlib import Path
import shutil

root = Path(__file__).resolve().parent
destination = root / 'public' / 'assets'
destination.mkdir(parents=True, exist_ok=True)
for source in (root / 'web').iterdir():
    if source.suffix in {'.css', '.js', '.svg'}:
        shutil.copy2(source, destination / source.name)

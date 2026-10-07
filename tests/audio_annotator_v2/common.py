"""Shared, dependency-free test configuration; the HTML itself has no dependencies."""
from pathlib import Path
import json
import os
import shutil

ROOT = Path(os.environ.get('AUDIO_V2_ROOT', Path(__file__).resolve().parents[2])).resolve()
F = Path(os.environ.get('AUDIO_V2_FIXTURES', ROOT / '.audio-v2-fixtures')).resolve()
OUT = Path(os.environ.get('AUDIO_V2_REPORTS', F / 'reports')).resolve()
OUT.mkdir(parents=True, exist_ok=True)
EXTRA_AUDIO = [Path(p).expanduser().resolve() for p in json.loads(os.environ.get('AUDIO_V2_FILES', '[]'))]
SAMPLE = ROOT / 'sample' / '251006_001_0002.WAV'
MEDIUM = next((p for p in EXTRA_AUDIO if p.name == 'FKW_small.wav'), F / 'medium_55s.wav')


def launch(playwright):
    """Use a selected/system Chromium or Playwright's installed Chromium."""
    executable = os.environ.get('AUDIO_V2_CHROMIUM') or shutil.which('chromium') or shutil.which('chromium-browser')
    options = dict(headless=True, args=['--autoplay-policy=no-user-gesture-required', '--disable-dev-shm-usage'])
    if executable:
        options['executable_path'] = executable
    return playwright.chromium.launch(**options)


def mount(page):
    """Default to a real file:// open. Injection is explicit for policy-restricted CI."""
    html = ROOT / 'audio_annotatorv2.html'
    if os.environ.get('AUDIO_V2_INJECT') == '1':
        page.set_content(html.read_text(encoding='utf-8'))
    else:
        page.goto(html.as_uri())


def existing(paths):
    """Retain stable test order; never silently skip an explicitly supplied file."""
    for path in [SAMPLE, *EXTRA_AUDIO]:
        if not path.is_file():
            raise FileNotFoundError(path)
    return list(dict.fromkeys(p for p in paths if p.is_file()))

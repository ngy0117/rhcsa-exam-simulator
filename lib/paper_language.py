"""Exam-paper language resources; no changes to the guest locale or exam state.

At seeding, render both languages with the same params. The controller's existing
prompt tar transfer includes both files, so node2 values never need to be inferred.
"""
import contextvars
import json
from pathlib import Path
from functools import lru_cache
import re

CURRENT = contextvars.ContextVar('paper_language', default='en')
CATALOG = Path(__file__).resolve().parents[1] / 'tui' / 'locales' / 'ko-KR.json'


def normalize(value):
    return 'ko-KR' if str(value).lower().replace('_', '-') in ('ko', 'ko-kr') else 'en'


def tr(message):
    if CURRENT.get() == 'en':
        return message
    return messages().get(message, message)


@lru_cache(maxsize=1)
def messages():
    # Resource changes take effect when the web server restarts.
    try:
        return json.loads(CATALOG.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def translated_source(directory, version):
    directory = Path(directory)
    # Never show generic translated wording when this release overrides the prompt.
    if (directory / ('prompt.rhel%s.txt' % version)).is_file():
        return directory / ('prompt.rhel%s.ko-KR.txt' % version)
    return directory / 'prompt.ko-KR.txt'


def render(directory, params_file, output, version):
    source = translated_source(directory, version)
    output = Path(output)
    if not source.is_file():
        # Remove stale caches if a translation was removed during an upgrade.
        output.unlink(missing_ok=True)
        return
    values = {}
    params_file = Path(params_file)
    if params_file.is_file():
        for line in params_file.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                values[key] = value
    text = source.read_text(encoding='utf-8')
    text = re.sub(r'\{\{(\w+)\}\}', lambda m: values.get(m[1], m[0]), text)
    # Atomic replacement keeps active readers from observing partially written text.
    tmp = output.with_suffix(output.suffix + '.tmp')
    tmp.write_text(text, encoding='utf-8')
    tmp.replace(output)


def prompt(tasks, prompts, tid, allow_translation=True):
    tasks, prompts = Path(tasks), Path(prompts)
    english = prompts / (tid + '.txt')
    if allow_translation and CURRENT.get() == 'ko-KR':
        cached = prompts / (tid + '.ko-KR.txt')
        if cached.is_file():
            return cached.read_text(encoding='utf-8', errors='replace')
        # Existing sessions predate bilingual caches: static translations are safe.
        # Parameterized tasks keep their rendered English values until next seed.
        source = translated_source(tasks / tid, release())
        if source.is_file():
            text = source.read_text(encoding='utf-8')
            if not re.search(r'\{\{\w+\}\}', text):
                return text
    for path in (english, tasks / tid / 'prompt.txt'):
        if path.is_file():
            return path.read_text(encoding='utf-8', errors='replace')
    return '(prompt not available)'


def release():
    import os
    if os.environ.get('RHCSA_RHEL'):
        return os.environ['RHCSA_RHEL']
    try:
        match = re.search(r'^VERSION_ID=["\']?(\d+)', Path('/etc/os-release').read_text(), re.M)
        return '10' if match and match[1] == '10' else '9'
    except OSError:
        return '9'


if __name__ == '__main__':
    import sys
    render(*sys.argv[1:])

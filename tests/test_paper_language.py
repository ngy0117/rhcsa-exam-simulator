"""Offline paper-language regression tests. Never seed tasks or invoke grading."""
import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import types
import unittest
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
import paper_language as lang


def exam_tasks():
    ids = set()
    for path in (ROOT / 'exams').glob('exam-r10*.list'):
        ids.update(line.split()[-1] for line in path.read_text().splitlines()
                   if line.strip() and not line.startswith('#'))
    return ids


class PaperLanguage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)
        self.prompts = self.state / 'prompts'
        self.prompts.mkdir()
        self.token = lang.CURRENT.set('en')

    def tearDown(self):
        lang.CURRENT.reset(self.token)
        self.tmp.cleanup()

    def test_all_rhel10_papers_have_complete_prompt_translations(self):
        self.assertEqual(len(exam_tasks()), 65)
        for tid in exam_tasks():
            source = ROOT / 'tasks' / tid
            translated = lang.translated_source(source, '10')
            self.assertTrue(translated.is_file(), tid)
            text = translated.read_text()
            self.assertRegex(text, '[가-힣]', tid)
            placeholders = lambda s: sorted(re.findall(r'\{\{\w+\}\}', s))
            self.assertEqual(placeholders((source / 'prompt.txt').read_text()), placeholders(text), tid)
            # Preserve concrete command/path/number tokens in source (manual semantic
            # review is still needed: this is a regression guard, not a translator).
            for token in re.findall(r'(?<![\w])(?:/[^\s,;()]+|\d+(?:\.\d+){2,3}(?:/\d+)?)(?![\w])', (source / 'prompt.txt').read_text()):
                if not token.endswith('.'):
                    self.assertIn(token.rstrip("`"), text, (tid, token))

    def test_exact_ui_template_format_contract(self):
        self.assertGreater(len(lang.messages()), 30)
        for english, korean in lang.messages().items():
            pattern = r'%(?:\([^)]+\))?[-+0-9.#]*[sdf]|%%'
            self.assertEqual(re.findall(pattern, english), re.findall(pattern, korean))
        lang.CURRENT.set('ko-KR')
        self.assertEqual(lang.tr('untranslated message'), 'untranslated message')

    def test_ui_templates_preserve_html_structure(self):
        from html.parser import HTMLParser
        class Tags(HTMLParser):
            def __init__(self):
                super().__init__()
                self.tags = []
            def handle_starttag(self, tag, attrs):
                self.tags.append((tag, attrs))
            def handle_endtag(self, tag):
                self.tags.append(('/' + tag, []))
        for english, korean in lang.messages().items():
            a, b = Tags(), Tags()
            a.feed(english)
            b.feed(korean)
            self.assertEqual(a.tags, b.tags)

    def test_shell_generates_both_languages_without_rolling_params(self):
        env = dict(os.environ, RHCSA_HOME=str(ROOT), RHCSA_STATE=str(self.state), RHCSA_RHEL='10')
        script = '. "$RHCSA_HOME/lib/common.sh"; gen_task_params flatpak-install "$RHCSA_TASKS/flatpak-install"; render_prompt flatpak-install "$RHCSA_TASKS/flatpak-install"'
        subprocess.run(['bash', '-c', script], env=env, check=True)
        params = self.state / 'params/flatpak-install.env'
        before = params.read_bytes()
        subprocess.run(['bash', '-c', script], env=env, check=True)
        self.assertEqual(before, params.read_bytes())
        self.assertTrue((self.prompts / 'flatpak-install.ko-KR.txt').exists())
        values = dict(line.split('=', 1) for line in before.decode().splitlines())
        for suffix in ('.txt', '.ko-KR.txt'):
            text = (self.prompts / ('flatpak-install' + suffix)).read_text()
            self.assertIn(values['REMOTE'], text)
            self.assertIn(values['APP_ID'], text)
            self.assertNotIn('{{', text)

    def test_node2_transfer_needs_no_private_params(self):
        remote = self.state / 'remote'
        remote.mkdir()
        params = remote / 'flatpak.env'
        params.write_text('REMOTE=node2-store\nAPP_ID=com.example.HelloRHCSA\n')
        output = remote / 'flatpak-install.ko-KR.txt'
        lang.render(ROOT / 'tasks/flatpak-install', params, output, '10')
        shutil.copy(output, self.prompts / output.name)
        params.unlink()
        lang.CURRENT.set('ko-KR')
        self.assertIn('node2-store', lang.prompt(ROOT / 'tasks', self.prompts, 'flatpak-install'))

    def test_troubleshooting_keeps_generated_symptoms(self):
        (self.prompts / 'selinux-port.txt').write_text('Generated fault: repair this symptom')
        (self.prompts / 'selinux-port.ko-KR.txt').write_text('기본 시험 문제')
        lang.CURRENT.set('ko-KR')
        self.assertEqual(lang.prompt(ROOT / 'tasks', self.prompts, 'selinux-port', allow_translation=False), 'Generated fault: repair this symptom')

    def test_version_specific_fallback_never_uses_wrong_translation(self):
        task = self.state / 'task'
        task.mkdir()
        (task / 'prompt.txt').write_text('generic English')
        (task / 'prompt.ko-KR.txt').write_text('일반 번역')
        (task / 'prompt.rhel10.txt').write_text('release 10 English')
        output = self.prompts / 'task.ko-KR.txt'
        lang.render(task, self.state / 'missing.env', output, '9')
        self.assertEqual(output.read_text(), '일반 번역')
        lang.render(task, self.state / 'missing.env', output, '10')
        self.assertFalse(output.exists())

    def test_existing_session_falls_back_to_actual_english_values(self):
        text = 'A Flatpak remote named "actual-node2-value".'
        (self.prompts / 'flatpak-install.txt').write_text(text)
        lang.CURRENT.set('ko-KR')
        self.assertEqual(lang.prompt(ROOT / 'tasks', self.prompts, 'flatpak-install'), text)

    def test_english_prompt_bytes_are_unchanged(self):
        for tid in exam_tasks():
            text = (ROOT / 'tasks' / tid / 'prompt.txt').read_text()
            (self.prompts / (tid + '.txt')).write_text(text)
            self.assertEqual(lang.prompt(ROOT / 'tasks', self.prompts, tid), text)

    def test_http_switch_preserves_session_and_marks_and_blocks_aids(self):
        spec = importlib.util.spec_from_file_location('web', ROOT / 'tui/exam_web.py')
        web = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(web)
        session = dict(exam='exam-r10-2node-01', start=1700000000, duration=9000,
                       tasks=['flatpak-install'], paper=[dict(id='flatpak-install', node='node2')])
        (self.state / 'session.json').write_text(json.dumps(session))
        marks = {'flatpak-install': 'revisit'}
        (self.state / 'marks.json').write_text(json.dumps(marks))
        (self.prompts / 'flatpak-install.txt').write_text('English actual value')
        (self.prompts / 'flatpak-install.ko-KR.txt').write_text('한국어 실제 값')
        before = {p.name: p.read_bytes() for p in self.state.glob('*.json')}
        web.ARGS = types.SimpleNamespace(session=str(self.state / 'session.json'), state=str(self.state),
                                       tasks=str(ROOT / 'tasks'), prompts=str(self.prompts))
        web.run_cli = lambda *args, **kwargs: self.fail('paper requests must not run CLI')
        server = web.ThreadingHTTPServer(('127.0.0.1', 0), web.H)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def request(language, path='/task?id=flatpak-install', data=None):
            headers = {'Cookie': 'rhcsa_paper_lang=' + language}
            req = urllib.request.Request('http://127.0.0.1:%d%s' % (server.server_port, path), data=data, headers=headers)
            with urllib.request.urlopen(req) as response:
                return response.read().decode()
        try:
            with concurrent.futures.ThreadPoolExecutor() as pool:
                texts = list(pool.map(request, ['en', 'ko-KR'] * 4))
            for index, text in enumerate(texts):
                self.assertIn('English actual value' if index % 2 == 0 else '한국어 실제 값', text)
                self.assertNotIn("onclick=\"aid(", text)
                self.assertNotIn("onclick=\"chk()", text)
                self.assertIn('1700009000', text)  # timer endpoint never changes
                self.assertIn('checked', text)     # marks survive switching
            self.assertIn('practice-only', request('ko-KR', '/api/aid', b'id=flatpak-install&kind=solution'))
            self.assertIn('practice aid', request('en', '/api/check', b'id=flatpak-install'))
            self.assertEqual(request('unsupported'), request('en'))
            self.assertIn('주요 구성 정보', request('ko-KR', '/config'))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.state.glob('*.json')})

if __name__ == '__main__':
    unittest.main()

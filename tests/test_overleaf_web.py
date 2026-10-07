"""Exercise HTTP session boundaries and output handling without live credentials."""
import argparse
import contextlib
import http.server
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock
import zipfile

spec = importlib.util.spec_from_file_location(
    'overleaf_web', Path(__file__).resolve().parents[1] / 'overleaf' / 'scripts' / 'overleaf_web.py')
web = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web)
PROJECT = 'a' * 24


class Server(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, code, body, cookie=None):
        self.send_response(code)
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/login':
            self.send(200, b'<meta name="ol-csrfToken" content="login-csrf">', 'sid=initial; HttpOnly')
        elif self.path == '/project':
            if self.headers.get('Cookie') != 'sid=authenticated':
                self.send(302, b'')
            else:
                self.send(200, b'<meta name="ol-csrfToken" content="project-csrf">')
        elif self.path.endswith('/download/zip'):
            self.send(200, self.server.archive)
        elif self.path.startswith('/build/output.pdf'):
            self.server.pdf_requested = True
            self.send(200, self.server.pdf)
        else:
            self.send(404, b'')

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
        self.server.requests.append((self.path, payload, dict(self.headers)))
        if self.path == '/login':
            valid = (payload.get('password') == 'test-only-password'
                     and payload.get('_csrf') == 'login-csrf'
                     and self.headers.get('Cookie') == 'sid=initial')
            self.send(200, b'{}', 'sid=authenticated; HttpOnly' if valid else None)
        elif self.path.endswith('/compile'):
            valid = (self.headers.get('Cookie') == 'sid=authenticated'
                     and self.headers.get('X-CSRF-Token') == 'project-csrf'
                     and '_csrf' not in payload)
            self.send(200 if valid else 403, json.dumps(self.server.compile_result).encode())
        else:
            self.send(404, b'')


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Server)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.server.requests = []
        self.server.pdf_requested = False
        self.server.pdf = b'%PDF-1.7\nmock server build\n'
        self.server.compile_result = {'status': 'success', 'outputFiles': [
            {'type': 'pdf', 'url': '/build/output.pdf?private=not-printed'}]}
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('main.tex', '\\documentclass{article}')
        self.server.archive = archive.getvalue()
        self.client = web.Client(self.url)

    def login(self):
        self.client.login('writer@example.org', 'test-only-password')

    def test_authenticated_source_export(self):
        self.login()
        with zipfile.ZipFile(io.BytesIO(self.client.download(PROJECT))) as z:
            self.assertEqual(z.namelist(), ['main.tex'])

    def test_login_200_does_not_prove_authentication(self):
        with self.assertRaises(web.OperationError):
            self.client.login('writer@example.org', 'wrong-test-password')

    def test_compile_uses_refreshed_csrf_and_requested_root(self):
        self.login()
        self.assertEqual(self.client.compile(PROJECT, 'xelatex', 'chapters/main.tex'),
                         self.server.pdf)
        _, body, headers = self.server.requests[-1]
        self.assertEqual(body['rootResourcePath'], 'chapters/main.tex')
        self.assertEqual(headers['X-CSRF-Token'], 'project-csrf')
        self.assertNotIn('_csrf', body)

    def test_failed_compile_never_downloads_old_pdf(self):
        self.login()
        self.server.compile_result['status'] = 'error'
        with self.assertRaises(web.OperationError):
            self.client.compile(PROJECT, 'pdflatex', 'main.tex')
        self.assertFalse(self.server.pdf_requested)

    def test_cross_origin_output_is_rejected_before_request(self):
        self.login()
        self.server.compile_result['outputFiles'][0]['url'] = 'https://other.example.org/file.pdf'
        with self.assertRaises(web.OperationError):
            self.client.compile(PROJECT, 'xelatex', 'main.tex')
        self.assertFalse(self.server.pdf_requested)

    def test_invalid_pdf_and_zip_are_rejected(self):
        self.login()
        self.server.pdf = b'<html>session expired</html>'
        with self.assertRaises(web.OperationError):
            self.client.compile(PROJECT, 'xelatex', 'main.tex')
        self.server.archive = b'<html>login</html>'
        with self.assertRaises(web.OperationError):
            self.client.download(PROJECT)

    def test_insecure_remote_or_http_override_is_rejected(self):
        for url, address in [('http://example.org', None),
                             (self.url, '192.0.2.1'),
                             ('https://user:secret@example.org', None)]:
            with self.subTest(url=url), self.assertRaises(web.OperationError):
                web.Client(url, address)

    def test_cli_saves_pdf_without_persisting_or_printing_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'paper.pdf'
            stdout, stderr = io.StringIO(), io.StringIO()
            with mock.patch('sys.stdin', io.StringIO('test-only-password\n')), \
                    contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                result = web.main(['--url', self.url, '--email', 'writer@example.org',
                                   '--password-stdin', 'compile', PROJECT, '--compiler',
                                   'xelatex', '--root', 'main.tex', '--output', str(target)])
            self.assertEqual(result, 0, stderr.getvalue())
            self.assertEqual(target.read_bytes(), self.server.pdf)
            self.assertEqual([p.name for p in Path(folder).iterdir()], ['paper.pdf'])
            self.assertNotIn('test-only-password', stdout.getvalue() + stderr.getvalue())
            self.assertNotIn('private=not-printed', stdout.getvalue() + stderr.getvalue())

    def test_existing_output_preserved_without_network_call(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'project.zip'
            target.write_bytes(b'keep me')
            with contextlib.redirect_stderr(io.StringIO()):
                result = web.main(['--url', self.url, '--email', 'writer@example.org',
                                   'download', PROJECT, '--output', str(target)])
            self.assertEqual(result, 1)
            self.assertEqual(target.read_bytes(), b'keep me')
            self.assertEqual(self.server.requests, [])

    def test_root_path_does_not_allow_escape(self):
        for value in ('../main.tex', '/main.tex', 'C:/main.tex', 'chapter\\main.tex'):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                web.root_document(value)


if __name__ == '__main__':
    unittest.main()

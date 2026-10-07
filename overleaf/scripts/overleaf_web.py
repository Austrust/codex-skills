#!/usr/bin/env python3
"""Version-scoped CE+ source export and compilation; no persistent credentials."""
import argparse
import getpass
import html.parser
import http.client
from http.cookies import SimpleCookie
import io
import ipaddress
import json
from pathlib import Path, PurePosixPath
import re
import socket
import ssl
import sys
import urllib.parse
import zipfile


class OperationError(Exception):
    pass


class CsrfParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.token = None

    def handle_starttag(self, tag, attrs):
        fields = dict(attrs)
        if fields.get('name') in ('ol-csrfToken', '_csrf'):
            self.token = fields.get('content', fields.get('value'))


def origin_tuple(url):
    return url.scheme, url.hostname, url.port or (443 if url.scheme == 'https' else 80)


class Client:
    def __init__(self, url, connect_address=None):
        self.url = urllib.parse.urlsplit(url)
        if (self.url.scheme not in ('https', 'http') or not self.url.hostname
                or self.url.username or self.url.password or self.url.query
                or self.url.fragment or self.url.path not in ('', '/')):
            raise OperationError('Use an origin URL without credentials, query, or path.')
        scheme, host, port = origin_tuple(self.url)
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = host == 'localhost'
        if scheme == 'http' and not loopback:
            raise OperationError('HTTP is allowed only for loopback testing.')
        if scheme == 'http' and connect_address:
            try:
                safe_address = ipaddress.ip_address(connect_address).is_loopback
            except ValueError:
                safe_address = connect_address == 'localhost'
            if not safe_address:
                raise OperationError('A loopback HTTP connection must remain on loopback.')
        self.origin = urllib.parse.urlunsplit((scheme, self.url.netloc, '', '', ''))
        self.host, self.port = host, port
        self.address = connect_address or host
        self.cookies = {}
        self.csrf = None

    def request(self, path, method='GET', payload=None):
        if not path.startswith('/') or path.startswith('//'):
            raise OperationError('Unexpected request path.')
        if self.url.scheme == 'https':
            context = ssl.create_default_context()
            connection = http.client.HTTPSConnection(self.host, self.port,
                                                      timeout=240, context=context)
            raw = socket.create_connection((self.address, self.port), timeout=20)
            try:
                connection.sock = context.wrap_socket(raw, server_hostname=self.host)
                connection.sock.settimeout(240)
            except Exception:
                raw.close()
                raise
        else:
            connection = http.client.HTTPConnection(self.address, self.port, timeout=240)
        headers = {'Origin': self.origin, 'Referer': self.origin + '/project',
                   'Host': self.url.netloc, 'Accept': '*/*'}
        if self.cookies:
            headers['Cookie'] = '; '.join(f'{k}={v}' for k, v in self.cookies.items())
        if self.csrf:
            headers['X-CSRF-Token'] = self.csrf
        body = None
        if payload is not None:
            body = json.dumps(payload).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        try:
            connection.request(method, path, body, headers)
            response = connection.getresponse()
            data = response.read(256 * 1024 * 1024 + 1)
            if len(data) > 256 * 1024 * 1024:
                raise OperationError('Response exceeds the helper limit of 256 MiB.')
            for key, value in response.getheaders():
                if key.lower() == 'set-cookie':
                    cookie = SimpleCookie()
                    cookie.load(value)
                    for name, morsel in cookie.items():
                        self.cookies[name] = morsel.value
            return response.status, data
        finally:
            connection.close()

    @staticmethod
    def require(status, expected, action):
        if status not in expected:
            raise OperationError(f'{action}: HTTP {status}; check compatibility and access.')

    def page_csrf(self, path):
        status, page = self.request(path)
        self.require(status, (200,), 'Session page')
        parser = CsrfParser()
        parser.feed(page.decode('utf-8'))
        if not parser.token:
            raise OperationError('CSRF token missing; this login flow is unsupported.')
        self.csrf = parser.token

    def login(self, email, password):
        self.page_csrf('/login')
        status, _ = self.request('/login', 'POST',
                                 {'email': email, 'password': password, '_csrf': self.csrf})
        self.require(status, (200, 302), 'Web login')
        # A 200 login response alone is not proof of authentication.
        self.page_csrf('/project')

    def download(self, project_id):
        status, data = self.request(f'/project/{project_id}/download/zip')
        self.require(status, (200,), 'Source export')
        if not zipfile.is_zipfile(io.BytesIO(data)):
            raise OperationError('Source export is not a ZIP archive.')
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if archive.testzip() is not None:
                raise OperationError('Source archive failed integrity verification.')
        return data

    def compile(self, project_id, compiler, root):
        status, data = self.request(f'/project/{project_id}/compile', 'POST',
                                    {'compiler': compiler, 'rootResourcePath': root,
                                     'check': 'silent'})
        self.require(status, (200,), 'Compilation')
        result = json.loads(data)
        if not isinstance(result, dict) or result.get('status') != 'success':
            raise OperationError('Compilation did not succeed; inspect the project build log.')
        files = result.get('outputFiles')
        if not isinstance(files, list):
            raise OperationError('Unexpected compilation response.')
        pdf = next((item for item in files if isinstance(item, dict)
                    and (item.get('type') == 'pdf'
                         or str(item.get('path', '')).endswith('.pdf'))), None)
        if not pdf or not isinstance(pdf.get('url'), str):
            raise OperationError('Compilation did not return a PDF URL.')
        target = urllib.parse.urlsplit(urllib.parse.urljoin(self.origin + '/', pdf['url']))
        if (origin_tuple(target) != origin_tuple(self.url)
                or target.username or target.password or target.fragment):
            raise OperationError('Refusing a PDF URL outside the authenticated origin.')
        path = target.path + ('?' + target.query if target.query else '')
        status, data = self.request(path)
        self.require(status, (200,), 'PDF download')
        if not data.startswith(b'%PDF-'):
            raise OperationError('Downloaded output is not a PDF.')
        return data


def project_id(value):
    if not re.fullmatch(r'[0-9a-fA-F]{24}', value):
        raise argparse.ArgumentTypeError('Expected a 24-character hexadecimal project ID.')
    return value


def root_document(value):
    path = PurePosixPath(value)
    if (not value or '\\' in value or path.is_absolute() or '..' in path.parts
            or not value.lower().endswith('.tex') or ':' in value):
        raise argparse.ArgumentTypeError('Expected a relative .tex document path.')
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--email', required=True)
    parser.add_argument('--connect-address', help='Optional DNS override; TLS/SNI still verified.')
    parser.add_argument('--password-stdin', action='store_true')
    commands = parser.add_subparsers(dest='action', required=True)
    for name in ('download', 'compile'):
        command = commands.add_parser(name)
        command.add_argument('project_id', type=project_id)
        command.add_argument('--output', type=Path, required=True)
        command.add_argument('--overwrite', action='store_true')
        if name == 'compile':
            command.add_argument('--compiler', choices=('pdflatex', 'xelatex', 'lualatex'),
                                 required=True)
            command.add_argument('--root', type=root_document, required=True)
    args = parser.parse_args(argv)
    client = None
    try:
        if args.output.exists() and not args.overwrite:
            raise OperationError('Output already exists; choose a new path or --overwrite.')
        client = Client(args.url, args.connect_address)
        password = (sys.stdin.readline().rstrip('\r\n') if args.password_stdin
                    else getpass.getpass('Web password (not saved): '))
        if not password:
            raise OperationError('No web password supplied.')
        client.login(args.email, password)
        password = None
        data = (client.download(args.project_id) if args.action == 'download'
                else client.compile(args.project_id, args.compiler, args.root))
        with args.output.open('wb' if args.overwrite else 'xb') as output:
            output.write(data)
        print(json.dumps({'action': args.action, 'status': 'success',
                          'output': str(args.output), 'bytes': len(data)}))
        return 0
    except OperationError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (OSError, ValueError, EOFError, http.client.HTTPException, zipfile.BadZipFile):
        print('Request or output failed; check network, access, response format, and output path.',
              file=sys.stderr)
        return 1
    finally:
        if client is not None:
            client.cookies.clear()
            client.csrf = None


if __name__ == '__main__':
    sys.exit(main())

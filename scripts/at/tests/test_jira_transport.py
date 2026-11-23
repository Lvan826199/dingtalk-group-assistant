import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.error
from unittest.mock import patch

FILE = Path(__file__).resolve().parents[1] / 'jira.py'
if Path(str(FILE) + '.new').exists():
    FILE = Path(str(FILE) + '.new')
loader = importlib.machinery.SourceFileLoader('jira_tested', str(FILE))
spec = importlib.util.spec_from_loader(loader.name, loader)
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)


class Response(io.BytesIO):
    def __init__(self, data, headers=None):
        super().__init__(json.dumps(data).encode()); self.headers = headers or {}


class JiraTransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        m.IP_CACHE = str(Path(self.tmp.name) / 'ip.json')
        m._DNS_CACHE = {'until': 0, 'addresses': []}

    def test_domestic_resolvers_before_foreign_and_cached(self):
        data = {'Status': 0, 'Answer': [{'type': 1, 'name': 'jira.example.com.', 'data': '180.165.48.76', 'TTL': 30}]}
        with patch.object(m.urllib.request, 'urlopen', side_effect=[OSError('unavailable'), Response(data)]) as opening:
            self.assertEqual(m._fallback_addresses(), ['180.165.48.76'])
        self.assertIn('dns.alidns.com', opening.call_args_list[0].args[0].full_url)
        self.assertIn('doh.pub', opening.call_args_list[1].args[0].full_url)
        self.assertEqual(json.loads(Path(m.IP_CACHE).read_text())['ttl'], 30)

    def test_cache_only_after_doh_fails_and_never_old_or_other_host(self):
        m._save_ip_cache('jira.example.com', ['180.165.48.76'], 30, 'test')
        with patch.object(m.urllib.request, 'urlopen', side_effect=OSError('unavailable')) as opening:
            self.assertEqual(m._fallback_addresses(), ['180.165.48.76'])
            self.assertEqual(opening.call_count, 4)
        data = json.loads(Path(m.IP_CACHE).read_text()); data['resolved_at'] = time.time() - 901
        Path(m.IP_CACHE).write_text(json.dumps(data))
        self.assertFalse(m._cached_addresses('jira.example.com'))
        m._save_ip_cache('other.example', ['180.165.48.76'], 30, 'test')
        self.assertFalse(m._cached_addresses('jira.example.com'))

    def test_curl_read_retry_bounded_original_host_and_no_auth_in_argv(self):
        req = m.urllib.request.Request(m.BASE + '/rest/api/2/myself', headers={'Authorization': 'Basic TEST_VALUE'})
        answers = [subprocess.CompletedProcess([], 28, b'', b'timeout'), subprocess.CompletedProcess([], 0, b'{"ok":true}\n200', b'')]
        with patch.object(m.socket, 'gethostbyname', side_effect=socket.gaierror()), patch.object(m, '_fallback_addresses', return_value=['180.165.48.76']), patch.object(m.subprocess, 'run', side_effect=answers) as run:
            self.assertEqual(m._curl_get(req), {'ok': True})
        self.assertEqual(run.call_count, 2)
        args = run.call_args.args[0]
        self.assertIn(req.full_url, args)
        self.assertIn('jira.example.com:18082:180.165.48.76', args)
        self.assertNotIn('TEST_VALUE', ' '.join(args))
        self.assertIn(b'TEST_VALUE', run.call_args.kwargs['input'])

    def test_http_auth_error_never_retried(self):
        req = m.urllib.request.Request(m.BASE + '/rest/api/2/myself')
        with patch.object(m.socket, 'gethostbyname', return_value='180.165.48.76'), patch.object(m.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'{}\n401', b'')) as run:
            self.assertRaises(SystemExit, m._curl_get, req)
            self.assertEqual(run.call_count, 1)

    def test_post_never_uses_curl_or_retries_unknown_write(self):
        with patch.object(m, 'auth', return_value='Basic TEST'), patch.object(m, '_curl_get') as curl, patch.object(m, 'open_url', side_effect=TimeoutError()) as opening:
            self.assertRaises(TimeoutError, m.call, 'POST', '/rest/api/2/issue/BUG-845/comment', {'body': 'test'})
            curl.assert_not_called(); self.assertEqual(opening.call_count, 1)

    def test_system_dns_retry_not_for_unrelated_domain(self):
        with patch.object(m.urllib.request, 'urlopen', side_effect=urllib.error.URLError(socket.gaierror())), patch.object(m, '_fallback_addresses') as fallback:
            self.assertRaises(urllib.error.URLError, m.open_url, 'http://other.example/')
            fallback.assert_not_called()


if __name__ == '__main__':
    unittest.main()

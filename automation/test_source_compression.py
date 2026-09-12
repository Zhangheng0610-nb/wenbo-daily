import gzip
import zlib
import unittest
from unittest.mock import patch, MagicMock
from automation.backfill_monitoring import decode_source_response, fetch

class SourceCompressionTests(unittest.TestCase):
    def test_gzip_header_and_missing_header_recover_readable_html(self):
        expected='<a href="/2026/09/11/news.html">博物馆新馆开放</a>'
        for header in ('gzip',''):
            self.assertEqual(decode_source_response(gzip.compress(expected.encode()),header),expected)
    def test_gzip_is_decoded_before_legacy_chinese_charset(self):
        self.assertEqual(decode_source_response(gzip.compress('文物保护'.encode('gb18030')),'gzip'),'文物保护')
    def test_uncompressed_and_deflate(self):
        self.assertEqual(decode_source_response(b'<html>news</html>'),'<html>news</html>')
        self.assertEqual(decode_source_response(zlib.compress(b'<html>news</html>'),'deflate'),'<html>news</html>')
    def test_corrupt_and_unsupported_payloads_fail_instead_of_becoming_gibberish(self):
        for raw,header in [(b'not gzip','gzip'),(b'compressed','br'),(zlib.compress(b'news')[:-2],'deflate')]:
            with self.subTest(header=header),self.assertRaises((ValueError,OSError,EOFError)):
                decode_source_response(raw,header)
    def test_compression_bomb_is_bounded(self):
        with patch('automation.backfill_monitoring.MAX_SOURCE_BYTES',100):
            for raw,header in [(gzip.compress(b'x'*1000),'gzip'),(zlib.compress(b'x'*1000),'deflate')]:
                with self.assertRaises(ValueError):decode_source_response(raw,header)
    def test_real_fetch_path_passes_content_encoding_to_decoder(self):
        response=MagicMock();response.__enter__.return_value=response
        response.headers={'Content-Encoding':'gzip'}
        response.read.return_value=gzip.compress('真实新闻'.encode())
        opener=MagicMock();opener.open.return_value=response
        with patch('automation.backfill_monitoring.source_opener',return_value=opener):
            self.assertEqual(fetch('https://example.org/news/'),'真实新闻')

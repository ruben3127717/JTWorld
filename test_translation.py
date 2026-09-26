import unittest
from unittest.mock import patch

import httpx
import main


class TranslationTests(unittest.TestCase):
    def setUp(self):
        main.translate.cache_clear()
        main._google_retry_after = 0

    def test_rate_limit_falls_back_cools_down_and_caches(self):
        with patch.object(main, 'google_translate', side_effect=RuntimeError('TooManyRequests')) as google, \
             patch.object(main, 'mymemory_translate', return_value='Bonjour') as backup:
            self.assertEqual(main.translate('Hello', 'en', 'fr'), 'Bonjour')
            self.assertEqual(main.translate('Hello', 'en', 'fr'), 'Bonjour')
            main.translate('Good morning', 'en', 'fr')
            self.assertEqual(google.call_count, 1)
            self.assertEqual(backup.call_count, 2)

    def test_unicode_chunks_preserve_text_and_byte_limit(self):
        for text in ['hello world ' * 200, '\u65e5\u672c\u8a9e' * 400, '\u043f\u0440\u0438\u0432\u0435\u0442 ' * 200]:
            chunks = list(main.translation_chunks(text))
            self.assertEqual(''.join(chunks), text)
            self.assertTrue(all(len(chunk.encode('utf-8')) <= 500 for chunk in chunks))

    def test_quota_message_never_becomes_spoken_translation(self):
        response = httpx.Response(200, request=httpx.Request('GET', 'https://example.com'),
                                  json={'quotaFinished': True, 'responseStatus': 200,
                                        'responseData': {'translatedText': 'QUOTA EXCEEDED'}})
        with patch.object(httpx.Client, 'get', return_value=response):
            with self.assertRaisesRegex(RuntimeError, 'quota'):
                main.mymemory_translate('Hello', 'en', 'fr')

    def test_failed_translation_retries_existing_transcript(self):
        with patch.object(main, 'translate', side_effect=[RuntimeError('offline'), 'Bonjour']) as translate, \
             patch('builtins.input', return_value='y'):
            self.assertEqual(main.translate_with_retry('Hello', 'en', 'fr'), 'Bonjour')
            self.assertEqual(translate.call_count, 2)
            translate.assert_called_with('Hello', 'en', 'fr')

    def test_empty_provider_result_is_rejected(self):
        response = httpx.Response(200, request=httpx.Request('GET', 'https://example.com'),
                                  json={'responseStatus': 200,
                                        'responseData': {'translatedText': ''}})
        with patch.object(httpx.Client, 'get', return_value=response):
            with self.assertRaisesRegex(RuntimeError, 'no text'):
                main.mymemory_translate('Hello', 'en', 'fr')

    def test_empty_memory_entry_uses_translated_alternative(self):
        response = httpx.Response(200, request=httpx.Request('GET', 'https://example.com'),
                                  json={'responseStatus': 200,
                                        'responseData': {'translatedText': ''},
                                        'matches': [
                                            {'translation': 'hola buenos dias', 'match': 0.96},
                                            {'translation': 'Hello good day', 'match': 0.95}]})
        with patch.object(httpx.Client, 'get', return_value=response):
            self.assertEqual(main.mymemory_translate('Hola, buenos dias.', 'es', 'en'),
                             'Hello good day')


if __name__ == '__main__':
    unittest.main()

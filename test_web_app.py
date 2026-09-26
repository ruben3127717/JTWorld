"""API integration tests: provider calls are replaced to avoid spending credits."""
import io
import unittest
import wave
from unittest.mock import patch

import web_app


class WebAppTests(unittest.TestCase):
    def setUp(self):
        self.client = web_app.app.test_client()

    def test_home_and_status_do_not_expose_credentials(self):
        home = self.client.get('/')
        self.assertEqual(home.status_code, 200)
        self.assertIn(b'Parla', home.data)
        status = self.client.get('/api/status').get_json()
        self.assertEqual(len(status['languages']), 5)
        self.assertNotIn('api_key', status)
        for path in ['/.env', '/assets/../.env', '/main.py']:
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_translation_uses_selected_languages(self):
        with patch.object(web_app.translator, 'translate', return_value='Bonjour') as translate:
            response = self.client.post('/api/translate', json={
                'text': ' Hello ', 'source': 'en', 'target': 'fr'})
        self.assertEqual(response.get_json(), {'text': 'Bonjour'})
        translate.assert_called_once_with('Hello', 'en', 'fr')

    def test_invalid_input_never_calls_provider(self):
        with patch.object(web_app.translator, 'translate') as translate:
            for data in [None, [], {}, {'text': ' '},
                         {'text': 'Hello', 'source': 'en', 'target': 'zz'},
                         {'text': 'a'*3001, 'source': 'en', 'target': 'fr'}]:
                self.assertEqual(self.client.post('/api/translate', json=data).status_code, 400)
            translate.assert_not_called()

    def test_external_origin_is_rejected(self):
        response = self.client.post('/api/speech', json={'text': 'Hello', 'target': 'en'},
                                    headers={'Origin': 'https://unrelated.example'})
        self.assertEqual(response.status_code, 403)

    def test_voice_failure_preserves_useful_error(self):
        with patch.object(web_app.translator, 'API_KEY', 'test-secret'), \
             patch.object(web_app.translator, 'generate_speech', side_effect=RuntimeError('Quota limit reached.')):
            response = self.client.post('/api/speech', json={'text': 'Bonjour', 'target': 'fr'})
        self.assertEqual(response.status_code, 502)
        self.assertIn('Quota', response.get_json()['error'])

    def test_audio_is_returned_to_browser_without_server_playback(self):
        with patch.object(web_app.translator, 'API_KEY', 'test-secret'), \
             patch.object(web_app.translator, 'generate_speech', return_value=b'MP3-audio') as generate, \
             patch.object(web_app.translator, 'play_audio') as play:
            response = self.client.post('/api/speech', json={'text': 'Bonjour', 'target': 'fr'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'audio/mpeg')
        self.assertEqual(response.data, b'MP3-audio')
        self.assertEqual(generate.call_args.args[1:], ('Bonjour', 'fr'))
        play.assert_not_called()

    def test_browser_wav_is_transcribed_in_source_language(self):
        output = io.BytesIO()
        with wave.open(output, 'wb') as recording:
            recording.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            recording.writeframes(b'\0\0' * 16000)
        with patch.object(web_app.translator.sr.Recognizer, 'recognize_google', return_value='Hola') as recognize:
            response = self.client.post('/api/transcribe', data={
                'source': 'es', 'audio': (io.BytesIO(output.getvalue()), 'recording.wav')})
        self.assertEqual(response.get_json(), {'text': 'Hola'})
        self.assertEqual(recognize.call_args.kwargs['language'], 'es-ES')

    def test_invalid_recording_is_rejected(self):
        response = self.client.post('/api/transcribe', data={
            'source': 'en', 'audio': (io.BytesIO(b'not a wav'), 'recording.wav')})
        self.assertEqual(response.status_code, 400)

    def test_parallel_request_is_rejected_without_queuing_charges(self):
        web_app.provider_lock.acquire()
        try:
            response = self.client.post('/api/speech', json={'text': 'Hello', 'target': 'en'})
            self.assertEqual(response.status_code, 409)
        finally:
            web_app.provider_lock.release()


if __name__ == '__main__':
    unittest.main()

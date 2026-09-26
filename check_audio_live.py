"""Manual live check. Running this generates short phrases using API credits."""
import main


def run():
    if not main.API_KEY:
        raise RuntimeError('Set ELEVENLABS_API_KEY before running this live check.')
    client = main.ElevenLabs(api_key=main.API_KEY, timeout=30)
    samples = {'ru': '\u041f\u0440\u0438\u0432\u0435\u0442.', 'es': 'Hola.',
               'ja': '\u3053\u3093\u306b\u3061\u306f\u3002', 'fr': 'Bonjour.'}
    main.LAST_AUDIO_PATH.parent.mkdir(parents=True, exist_ok=True)
    for language, text in samples.items():
        audio = main.generate_speech(client, text, language)
        output = main.LAST_AUDIO_PATH.parent / f'check_{language}.mp3'
        output.write_bytes(audio)
        sound = main.pygame.mixer.Sound(str(output))
        print(f'{language}: {len(audio)} bytes, {sound.get_length():.2f} seconds')


if __name__ == '__main__':
    main.pygame.mixer.init()
    try:
        run()
    finally:
        main.pygame.mixer.quit()

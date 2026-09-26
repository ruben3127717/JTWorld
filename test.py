def main():
    # Generate only when this script is run directly, never on import.
    import main as translator

    if not translator.API_KEY:
        raise RuntimeError("Set ELEVENLABS_API_KEY before running the audio test.")

    translator.AUDIO_OUTPUT_DEVICE = translator.choose_output_device()
    client = translator.ElevenLabs(api_key=translator.API_KEY, timeout=60)
    translator.synthesize_and_play(client, "Audio test. The translator is ready.", "en")


if __name__ == "__main__":
    main()

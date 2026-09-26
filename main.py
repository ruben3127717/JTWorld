"""Translate one microphone recording at a time. Internet access required.

Audio/text are sent to Google, MyMemory (fallback), and ElevenLabs.
Use Python 3.11 or 3.12.
"""
import multiprocessing as mp
import os
from pathlib import Path
import time
from functools import lru_cache
from html import unescape
from dotenv import load_dotenv

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
load_dotenv(Path(__file__).resolve().with_name(".env"))
import httpx
import pygame
import speech_recognition as sr
from deep_translator import GoogleTranslator
from elevenlabs.client import ElevenLabs
from elevenlabs.core.api_error import ApiError

# Load from .env; an already-set process environment variable takes precedence.
API_KEY = os.environ.get("ELEVENLABS_API_KEY", "").strip()
# Seconds of silence before recording ends. Increase for longer speaking pauses.
END_OF_SPEECH_PAUSE_SECONDS = 1.5

LANGUAGES = {
    
    "1": ("English", "en", "en-US"),
    "2": ("Russian", "ru", "ru-RU"),
    "3": ("Spanish", "es", "es-ES"),
    "4": ("Japanese", "ja", "ja-JP"),
    "5": ("French", "fr", "fr-FR"),
}
# Voice selected by the TARGET language, using your supplied ElevenLabs IDs.
# Edit the corresponding entry here to change a language's voice.
VOICE_IDS = {
    "en": "KYEC757088OvL0vzRaIG",  # English
    "ru": "6gs4Nc3jAINHpczl2vtf",  # Russian
    "es": "aZilAbZ5tl8i9lA1EF02",  # Spanish
    "ja": "T7yYq3WpB94yAuOXraRi",  # Japanese
    "fr": "Qrl71rx6Yg8RvyPYRGCQ",  # French
}
# Used only if ElevenLabs explicitly rejects a selected voice as paid-only.
FALLBACK_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"  # Premade George, multilingual
_paid_only_voices = set()
AUDIO_OUTPUT_DEVICE = None  # None uses Windows' default; chosen at startup.
LAST_AUDIO_PATH = Path(__file__).resolve().parent / "output_audio" / "last_translation.mp3"


def choose_output_device():
    """Let the user route speech to speakers instead of an unintended monitor."""
    from pygame._sdl2.audio import get_audio_device_names

    try:
        pygame.mixer.init()
        devices = list(get_audio_device_names(False))
    except pygame.error as exc:
        raise RuntimeError("No audio output available. Connect speakers/headphones.") from exc
    finally:
        pygame.mixer.quit()
    print("\nChoose where to play speech:")
    print("  0. Windows default")
    for index, device in enumerate(devices, 1):
        print(f"  {index}. {device}")
    while True:
        choice = input("Output device [Enter = Windows default]: ").strip() or "0"
        if choice.isdigit() and 0 <= int(choice) <= len(devices):
            return devices[int(choice) - 1] if int(choice) else None
        print("Please choose one of the listed numbers.")


def api_error_details(error):
    body = error.body if isinstance(error.body, dict) else {}
    detail = body.get("detail", body)
    def redact(value):
        value = str(value)
        return value.replace(API_KEY, "[redacted]") if API_KEY else value
    if not isinstance(detail, dict):
        return "", redact(detail)[:400]
    code = detail.get("code") or detail.get("status") or ""
    message = redact(detail.get("message", ""))[:400]
    return code, message


def generate_speech(client, text, target):
    """Fallback only after an explicit paid-voice rejection, never on quota."""
    selected = VOICE_IDS[target]
    voice = FALLBACK_VOICE_ID if selected in _paid_only_voices else selected
    while True:
        try:
            audio = b"".join(client.text_to_speech.convert(
                voice_id=voice, text=text,
                model_id="eleven_multilingual_v2",
                output_format="mp3_44100_128",
                request_options={"max_retries": 0},
            ))
            if not audio:
                raise RuntimeError("ElevenLabs returned no audio.")
            return audio
        except ApiError as exc:
            code, detail = api_error_details(exc)
            paid_voice = code == "paid_plan_required" or (
                code == "payment_required" and "library voices" in detail.lower()
            )
            if paid_voice and voice != FALLBACK_VOICE_ID:
                _paid_only_voices.add(selected)
                print("Selected voice requires a paid plan; using premade George "
                      "for this language.")
                voice = FALLBACK_VOICE_ID
                continue
            if "quota" in code or "quota" in detail.lower():
                message = "ElevenLabs quota limit reached."
            elif paid_voice or exc.status_code == 402:
                message = "ElevenLabs requires a paid plan for this request."
            elif exc.status_code == 429:
                message = "ElevenLabs rate limit reached. Wait and try again."
            elif exc.status_code in (401, 403):
                message = "ElevenLabs rejected the key or its permissions."
            elif exc.status_code == 404:
                message = "Voice unavailable. Update VOICE_IDS."
            else:
                message = f"ElevenLabs request failed (HTTP {exc.status_code})."
            raise RuntimeError(f"{message} {detail}".strip()) from exc
        except httpx.RequestError as exc:
            raise RuntimeError("ElevenLabs connection failed or timed out.") from exc


def play_audio(output):
    try:
        pygame.mixer.init(devicename=AUDIO_OUTPUT_DEVICE)
        pygame.mixer.music.load(str(output))
        pygame.mixer.music.set_volume(1.0)
        pygame.mixer.music.play()
        print(f"Playing through: {AUDIO_OUTPUT_DEVICE or 'Windows default'}")
        clock = pygame.time.Clock()
        while pygame.mixer.music.get_busy():
            clock.tick(20)
    except pygame.error as exc:
        raise RuntimeError(f"Playback failed. Audio saved at {output}. "
                           "Choose another output device on restart.") from exc
    finally:
        pygame.mixer.quit()

def choose_language(prompt):
    print("\n" + prompt)
    for number, (name, _, _) in LANGUAGES.items():
        print(f"  {number}. {name}")
    while True:
        choice = input("Enter 1-5 (q to quit): ").strip().lower()
        if choice == "q":
            raise EOFError
        if choice in LANGUAGES:
            return LANGUAGES[choice]
        print("Please enter a number from 1 to 5.")


def record_and_transcribe(locale):
    recognizer = sr.Recognizer()
    recognizer.pause_threshold = END_OF_SPEECH_PAUSE_SECONDS
    recognizer.operation_timeout = 20
    try:
        with sr.Microphone() as microphone:
            print("Stay quiet for one second while the microphone calibrates...")
            recognizer.adjust_for_ambient_noise(microphone, duration=1)
            print(f"Speak now (up to 20 seconds); stay silent for "
                  f"{END_OF_SPEECH_PAUSE_SECONDS:g} seconds to finish.")
            audio = recognizer.listen(microphone, timeout=10, phrase_time_limit=20)
    except sr.WaitTimeoutError as exc:
        raise RuntimeError("No speech detected within 10 seconds.") from exc
    except (OSError, AttributeError) as exc:
        raise RuntimeError(
            "Microphone unavailable. Check PyAudio, your default input device, "
            "and microphone permissions."
        ) from exc
    try:
        print("Transcribing...")
        text = recognizer.recognize_google(audio, language=locale)
        if not text.strip():
            raise RuntimeError("Empty transcription. Please try again.")
        return text
    except sr.UnknownValueError as exc:
        raise RuntimeError("Speech was unclear. Please try again.") from exc
    except sr.RequestError as exc:
        raise RuntimeError("Speech recognition failed. Check your connection.") from exc


def translation_worker(connection, text, source, target):
    """Separate process allows a stalled translation to be cancelled."""
    try:
        result = GoogleTranslator(source=source, target=target).translate(text)
        connection.send((True, result))
    except Exception as exc:
        connection.send((False, type(exc).__name__))
    finally:
        connection.close()


def google_translate(text, source, target):
    if source == target:
        return text
    # deep-translator does not expose a reliable per-request timeout.
    context = mp.get_context("spawn")
    reader, writer = context.Pipe(duplex=False)
    process = context.Process(
        target=translation_worker, args=(writer, text, source, target), daemon=True
    )
    process.start()
    writer.close()
    try:
        if not reader.poll(30):
            raise RuntimeError("Translation timed out after 30 seconds.")
        try:
            success, result = reader.recv()
        except EOFError as exc:
            raise RuntimeError("Translation process stopped unexpectedly.") from exc
        if not success:
            raise RuntimeError(f"Translation failed ({result}). Please try again.")
        if not isinstance(result, str) or not result.strip():
            raise RuntimeError("Translation service returned empty text.")
        return result
    finally:
        reader.close()
        process.join(timeout=1)
        if process.is_alive():
            process.terminate()
            process.join()
        process.close()


def translation_chunks(text, limit=500):
    """Respect MyMemory's UTF-8 byte limit, preferably splitting at spaces."""
    while text:
        chunk = text.encode("utf-8")[:limit].decode("utf-8", errors="ignore")
        if len(chunk) < len(text):
            boundary = chunk.rfind(" ")
            if boundary > 0:
                chunk = chunk[:boundary + 1]
        yield chunk
        text = text[len(chunk):]


def mymemory_translate(text, source, target):
    """Use the documented HTTPS API and reject quota/error responses."""
    translated = []
    deadline = time.monotonic() + 60
    with httpx.Client() as client:
        for chunk in translation_chunks(text):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("Backup translation timed out.")
            try:
                response = client.get(
                    "https://api.mymemory.translated.net/get",
                    params={"q": chunk, "langpair": f"{source}|{target}"},
                    timeout=min(15, remaining),
                )
                if response.status_code in (403, 429):
                    raise RuntimeError("Backup translation is currently rate limited.")
                response.raise_for_status()
                data = response.json()
                if data.get("quotaFinished"):
                    raise RuntimeError("Backup translation's daily quota is exhausted.")
                if str(data.get("responseStatus")) != "200":
                    raise RuntimeError("Backup translation service rejected the request.")
                result = data.get("responseData", {}).get("translatedText")
                # Some memory entries contain an empty translation. In that
                # case use a close, nonempty alternative supplied by the API.
                if not isinstance(result, str) or not result.strip():
                    for match in data.get("matches", []):
                        candidate = match.get("translation")
                        if (isinstance(candidate, str) and candidate.strip()
                                and ''.join(c for c in candidate.casefold() if c.isalnum())
                                != ''.join(c for c in chunk.casefold() if c.isalnum())
                                and float(match.get("match", 0)) >= 0.9):
                            result = candidate
                            break
                if not isinstance(result, str) or not result.strip():
                    raise RuntimeError("Backup translation returned no text.")
                translated.append(unescape(result).strip())
            except (httpx.HTTPError, ValueError, AttributeError) as exc:
                raise RuntimeError("Backup translation is unavailable. Try again later.") from exc
    return " ".join(translated)


_google_retry_after = 0.0


@lru_cache(maxsize=128)
def translate(text, source, target):
    """Cache successes and stop contacting Google temporarily after failure."""
    global _google_retry_after
    if not text.strip():
        raise RuntimeError("There is no text to translate.")
    if source == target:
        return text
    if time.monotonic() >= _google_retry_after:
        try:
            return google_translate(text, source, target)
        except RuntimeError:
            _google_retry_after = time.monotonic() + 300
            print("Google translation unavailable; switching to MyMemory.")
    return mymemory_translate(text, source, target)


def translate_with_retry(text, source, target):
    """Keep the transcript so a service failure never requires re-recording."""
    while True:
        try:
            return translate(text, source, target)
        except RuntimeError as exc:
            print(f"Translation error: {exc}")
            if input("Keep this phrase and retry? [y/N]: ").strip().lower() != "y":
                return None


def synthesize_and_play(client, text, target):
    text = text.strip()
    if not text:
        raise RuntimeError("No translated text to speak.")
    print(f"Sending {len(text)} characters to ElevenLabs.")
    audio = generate_speech(client, text, target)
    LAST_AUDIO_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAST_AUDIO_PATH.write_bytes(audio)
    print(f"Audio saved: {LAST_AUDIO_PATH}")
    play_audio(LAST_AUDIO_PATH)


def main():
    global AUDIO_OUTPUT_DEVICE
    print("Voice translator - press Ctrl+C to quit.")
    if not API_KEY:
        raise RuntimeError(
            "ELEVENLABS_API_KEY is not set. Add it to your Windows user "
            "environment variables, then reopen the terminal."
        )
    client = ElevenLabs(api_key=API_KEY, timeout=60)
    AUDIO_OUTPUT_DEVICE = choose_output_device()
    _, source, locale = choose_language("Which language will you speak?")
    while True:
        input("\nPress Enter when ready to record...")
        try:
            text = record_and_transcribe(locale)
            print(f"You said: {text}")
            name, target, _ = choose_language("Select the target language:")
            translated = translate_with_retry(text, source, target)
            if translated is not None:
                print(f"{name}: {translated}")
                synthesize_and_play(client, translated, target)
        except (RuntimeError, OSError) as exc:
            print(f"Error: {exc}")
        if input("\nTranslate another phrase? [y/N]: ").strip().lower() != "y":
            break


if __name__ == "__main__":
    mp.freeze_support()  # Supports Windows multiprocessing/frozen executables.
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nGoodbye!")

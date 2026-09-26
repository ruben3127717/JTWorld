"""Local browser interface for the existing voice translator.

Run with .venv312/Scripts/python.exe web_app.py or run-website.cmd.
Only web/ is served publicly; .env and Python source are never static assets.
"""
import io
import multiprocessing
import threading
import wave
from functools import wraps

from flask import Flask, jsonify, request, Response
from werkzeug.exceptions import HTTPException
import main as translator

app = Flask(__name__, static_folder="web", static_url_path="/assets")
app.config.update(MAX_CONTENT_LENGTH=6 * 1024 * 1024, TRUSTED_HOSTS=["127.0.0.1", "localhost"])
LANGUAGES = {code: {"name": name, "locale": locale}
             for name, code, locale in translator.LANGUAGES.values()}
provider_lock = threading.Lock()


@app.before_request
def restrict_origin():
    # Prevent other websites from spending credits against this local service.
    if request.method == "POST":
        origin = request.headers.get("Origin")
        if origin and origin != request.host_url.rstrip("/"):
            return jsonify(error="Open the translator from its local website."), 403


@app.after_request
def response_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'"
    )
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def provider_job(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        if not provider_lock.acquire(blocking=False):
            return jsonify(error="Another translation is running. Try again in a moment."), 409
        try:
            return function(*args, **kwargs)
        finally:
            provider_lock.release()
    return wrapped


def language(value):
    if not isinstance(value, str) or value not in LANGUAGES:
        raise ValueError("Choose a supported language.")
    return value


def payload(limit=3000):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("Send a valid translation request.")
    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Add some text or record your voice first.")
    if len(text) > limit:
        raise ValueError(f"Please keep your text under {limit:,} characters.")
    return data, text.strip()


@app.errorhandler(Exception)
def handle_error(error):
    if isinstance(error, HTTPException):
        return jsonify(error="Recording is too large." if error.code == 413 else error.description), error.code
    if isinstance(error, ValueError):
        return jsonify(error=str(error)), 400
    if isinstance(error, translator.sr.UnknownValueError):
        return jsonify(error="I couldn't make out the words. Try again, or type your message."), 422
    if isinstance(error, translator.sr.RequestError):
        return jsonify(error="Speech recognition is unavailable. Try typing your message."), 502
    if isinstance(error, RuntimeError):
        return jsonify(error=str(error).replace(translator.API_KEY, "[redacted]")
                       if translator.API_KEY else str(error)), 502
    app.logger.error("Request failed: %s", type(error).__name__)
    return jsonify(error="Something went wrong. Your text is still here; please try again."), 500


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/api/status")
def status():
    return jsonify(speech_ready=bool(translator.API_KEY), languages=LANGUAGES,
                   pause_seconds=translator.END_OF_SPEECH_PAUSE_SECONDS)


@app.post("/api/transcribe")
@provider_job
def transcribe():
    source = language(request.form.get("source"))
    upload = request.files.get("audio")
    if upload is None:
        raise ValueError("Record your voice first.")
    raw = upload.read()
    # Browser produces mono PCM WAV, so no server-side FFmpeg is needed.
    try:
        with wave.open(io.BytesIO(raw), "rb") as wav:
            duration = wav.getnframes() / wav.getframerate()
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or not 0.2 <= duration <= 31:
                raise ValueError("Record between 1 and 30 seconds of speech.")
    except (wave.Error, EOFError, ZeroDivisionError) as exc:
        raise ValueError("That recording could not be read. Please record again.") from exc
    recognizer = translator.sr.Recognizer()
    recognizer.operation_timeout = 20
    with translator.sr.AudioFile(io.BytesIO(raw)) as audio_file:
        audio = recognizer.record(audio_file)
    text = recognizer.recognize_google(audio, language=LANGUAGES[source]["locale"])
    return jsonify(text=text)


@app.post("/api/translate")
@provider_job
def translate():
    data, text = payload()
    source, target = language(data.get("source")), language(data.get("target"))
    return jsonify(text=translator.translate(text, source, target))


@app.post("/api/speech")
@provider_job
def speech():
    data, text = payload(limit=10000)
    target = language(data.get("target"))
    # Use the browser credential only for this request; never persist it or
    # replace the process-wide key used by the command-line translator.
    supplied_key = data.get("api_key", "")
    if not isinstance(supplied_key, str) or len(supplied_key) > 512:
        raise ValueError("Enter a valid ElevenLabs API key.")
    api_key = supplied_key.strip() or translator.API_KEY
    if not api_key:
        raise RuntimeError("Add your ElevenLabs API key above to enable audio. Text translation is available.")
    try:
        client = translator.ElevenLabs(api_key=api_key, timeout=45)
        audio = translator.generate_speech(client, text, target)
    except RuntimeError as exc:
        # Provider errors may echo credentials. Do not return them to the UI.
        return jsonify(error=str(exc).replace(api_key, "[redacted]")), 502
    except Exception:
        return jsonify(error="ElevenLabs could not generate audio. Check your key and try again."), 502
    fallback = translator.VOICE_IDS[target] in translator._paid_only_voices
    return Response(audio, mimetype="audio/mpeg", headers={
        "X-Voice-Fallback": "true" if fallback else "false",
        "Content-Disposition": 'inline; filename="translation.mp3"',
    })


if __name__ == "__main__":
    multiprocessing.freeze_support()
    from waitress import serve
    print("Open http://127.0.0.1:8765 — Ctrl+C to stop", flush=True)
    serve(app, host="127.0.0.1", port=8765, threads=4)

# JT World

A local voice translation studio. Speak or type in English, Russian, Spanish,
Japanese, or French, then read and listen to the translated message.

## Start the website

Double-click **run-website.cmd**. Keep the terminal open while using the app.
The website opens at **http://127.0.0.1:8765**.

Allow microphone access when prompted. Record up to 30 seconds; choose the
silence duration or stop manually. Text mode supports up to 3,000 characters.
You can edit a transcript, replay speech without a new API call, copy a
translation, download an MP3, and revisit the last 20 translations in this tab.

## Setup on another machine

Use Python 3.12 and install `requirements.txt` in a virtual environment. Create
an optional `.env` beside `main.py` with `ELEVENLABS_API_KEY=your_key`, or paste
your key into the website’s ElevenLabs API key box. Run `python web_app.py`.
The included Windows launcher uses the existing `.venv312` environment.

An existing environment variable takes precedence over `.env`. If changing the
key in `.env` appears to have no effect, remove the old process variable in
PowerShell with `Remove-Item Env:ELEVENLABS_API_KEY -ErrorAction SilentlyContinue`
before launching Python, or update/remove the saved Windows user variable.

## How it works

The browser captures mono WAV audio and sends it to the local Flask server.
The server uses SpeechRecognition for Google transcription, the existing Google
translation / MyMemory fallback, and the ElevenLabs SDK for speech. Speech plays
in the browser using the system's audio output. No FFmpeg is needed by the web app.

The custom voice for the target language is tried first. Paid-only voices fall
back to premade George on the free plan. Translation remains visible if speech
generation fails. Disable “Read translation aloud” to translate without using
ElevenLabs credits, then press Listen when needed.

Only the `web` folder is served. Keys entered in the website are held only in the
current tab, cleared on reload, and never saved to browser storage or disk. Clear
the field with **Clear key**. Audio requests pass the key through the loopback
server to ElevenLabs over HTTPS for authentication; the server does not save it.
The optional `.env` key is never returned to the browser.
Recordings and generated audio are held in memory for this web workflow; tab
history clears on reload. Providers receive audio/text as described in the app.

Waitress serves the application on loopback only. This is a personal local app;
public deployment would require authentication, HTTPS, and per-user quotas.
The original command-line translator remains available via `run-translator.cmd`.

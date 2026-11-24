#!/usr/bin/env python3
"""ai_bridge.py - Asterisk AGI bridge: caller audio -> STT -> free text LLM -> TTS -> playback.

Demo loop only (max 3 rounds per call). Runs under Asterisk AGI; the dialplan
answers the channel first, then runs this script for extension 1001.

Pipeline (all local/free):
  RECORD FILE (caller speech, wav) -> Vosk small-en model (STT)
  -> Pollinations free text API (https://text.pollinations.ai, no key)
  -> Piper TTS (local onnx voice) -> sox resample to 8kHz -> STREAM FILE

No PSTN is involved: this answers only local SIP extension 1001.
Logs rounds (text + timings) to logs/ai_calls.log - no audio content is logged.
"""
import os
import sys
import time
import json
import urllib.parse
import urllib.request
import subprocess

BASE = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
DATA = os.path.join(BASE, "data")
REC = os.path.join(BASE, "recordings")
LOG = os.path.join(BASE, "logs", "ai_calls.log")
VENV_PY = os.path.join(BASE, "venv-ai", "bin", "python")
MODEL = os.path.join(BASE, "models", "vosk-model-small-en-us-0.15")
PIPER_VOICE = os.path.join(BASE, "models", "en_US-lessac-medium.onnx")
MAX_ROUNDS = 3
LLM_URL = "https://text.pollinations.ai/"

# ---- minimal AGI helpers ----
def agi_send(cmd):
    sys.stdout.write(cmd + "\n")
    sys.stdout.flush()
    resp = sys.stdin.readline().strip()
    return resp

def agi_get_var(name):
    return agi_send(f"GET VARIABLE {name}")

def log(msg):
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"[{ts}] {msg}\n")

def run(cmd, timeout=120):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

def stt(wav_path):
    """Vosk STT on a wav file; returns recognized text (may be '').
    The small-en model is 16kHz; Asterisk records at 8kHz, so resample first."""
    wav16 = wav_path + ".16k.wav"
    r = run(["sox", wav_path, "-r", "16000", "-c", "1", "-b", "16", wav16], timeout=30)
    if r.returncode != 0:
        raise RuntimeError(f"sox 8k->16k failed: {r.stderr[-200:]}")
    code = (
        "import sys, json, wave\n"
        "from vosk import Model, KaldiRecognizer\n"
        f"m = Model(r'{MODEL}')\n"
        f"wf = wave.open(r'{wav16}', 'rb')\n"
        "rec = KaldiRecognizer(m, 16000)\n"
        "text = ''\n"
        "while True:\n"
        "    data = wf.readframes(4000)\n"
        "    if len(data) == 0: break\n"
        "    if rec.AcceptWaveform(data):\n"
        "        text += json.loads(rec.Result()).get('text','') + ' '\n"
        "text += json.loads(rec.FinalResult()).get('text','')\n"
        "print(text.strip())\n"
    )
    r = run([VENV_PY, "-c", code], timeout=90)
    return r.stdout.strip()

def llm(prompt):
    """Pollinations free text API. Short reply, one or two sentences."""
    full = ("You are a helpful phone assistant. Reply in one or two short "
            f"sentences, plain English. User said: {prompt}")
    url = LLM_URL + urllib.parse.quote(full) + "?model=openai"
    req = urllib.request.Request(url, headers={"User-Agent": "ai-phone-system/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", "replace").strip()

def tts(text, out_wav_8k):
    """Piper TTS -> wav, resampled to 8kHz mono for Asterisk playback."""
    tmp = out_wav_8k + ".piper.wav"
    # piper python module reads the text from stdin
    p = subprocess.run([VENV_PY, "-m", "piper", "--model", PIPER_VOICE,
                        "--output_file", tmp],
                       input=text, capture_output=True, text=True, timeout=90)
    if p.returncode != 0 or not os.path.exists(tmp):
        raise RuntimeError(f"piper failed: {p.stderr[-300:]}")
    r2 = run(["sox", tmp, "-r", "8000", "-c", "1", "-b", "16", out_wav_8k], timeout=30)
    os.path.exists(tmp) and os.remove(tmp)
    if r2.returncode != 0:
        raise RuntimeError(f"sox resample failed: {r2.stderr[-300:]}")
    return out_wav_8k

def main():
    # Read AGI environment (ends with a blank line).
    env = {}
    while True:
        line = sys.stdin.readline()
        if not line or line.strip() == "":
            break
        if ":" in line:
            k, v = line.split(":", 1)
            env[k.strip()] = v.strip()
    caller = env.get("agi_callerid", "?")
    unique = env.get("agi_uniqueid", str(int(time.time())))
    log(f"call start caller={caller} uniqueid={unique}")
    t0 = time.time()
    try:
        # Greeting (pre-generated if present, else synthesize now).
        greet = os.path.join(REC, "greeting.wav")
        if not os.path.exists(greet):
            tts("Hello, this is the A I assistant. How can I help you?", greet)
        agi_send(f'STREAM FILE {greet[:-4]} "#"')
        for rnd in range(1, MAX_ROUNDS + 1):
            infile = os.path.join(REC, f"ai_in_{unique}_{rnd}.wav")
            # RECORD FILE <file> <format> <escape> <timeout_ms> [offset] [beep] [silence]
            # silence: s=2 -> stop after 2s of silence; timeout 8s.
            resp = agi_send(f"RECORD FILE {infile[:-4]} wav # 8000 0 1 s=2")
            log(f"round {rnd} record resp: {resp}")
            if not os.path.exists(infile):
                log(f"round {rnd}: no recording file")
                break
            t_stt = time.time()
            text = stt(infile)
            dt_stt = time.time() - t_stt
            log(f"round {rnd} STT ({dt_stt:.1f}s): {text!r}")
            if not text:
                bye = os.path.join(REC, "nocatch.wav")
                if not os.path.exists(bye):
                    tts("Sorry, I did not catch that. Goodbye.", bye)
                agi_send(f'STREAM FILE {bye[:-4]} "#"')
                break
            t_llm = time.time()
            try:
                reply = llm(text)
            except Exception as e:
                reply = "Sorry, the answering service is unavailable right now."
                log(f"round {rnd} LLM error: {e}")
            dt_llm = time.time() - t_llm
            log(f"round {rnd} LLM ({dt_llm:.1f}s): {reply!r}")
            out = os.path.join(REC, f"ai_out_{unique}_{rnd}.wav")
            t_tts = time.time()
            try:
                tts(reply, out)
            except Exception as e:
                log(f"round {rnd} TTS error: {e}")
                break
            dt_tts = time.time() - t_tts
            log(f"round {rnd} TTS ({dt_tts:.1f}s) -> {out}")
            agi_send(f'STREAM FILE {out[:-4]} "#"')
            if any(w in text.lower() for w in ("goodbye", "bye", "hang up")):
                break
        log(f"call end total={time.time()-t0:.1f}s")
    except Exception as e:
        log(f"ERROR: {e}")

if __name__ == "__main__":
    main()

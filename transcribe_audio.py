#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["click", "rich", "faster-whisper", "av<16", "pyannote.audio"]
# ///
"""Transcribe audio/video (mp3, m4a, mp4, mov, wav, ...) with optional timestamps and speaker labels.

    ./transcribe_audio.py local talk.m4a -t -o out.txt              # on this machine (private, free)
    HF_TOKEN=hf_... ./transcribe_audio.py local talk.m4a -s -t      # + speaker labels (pyannote needs a HF token)

    ./transcribe_audio.py cloud --list-models                       # speech-to-text models on OpenRouter
    OPENROUTER_API_KEY=sk-or-... ./transcribe_audio.py cloud talk.m4a -s -t   # no HF token needed

    ./transcribe_audio.py audio-compress talk.m4a -o talk_small.ogg # ~11 MB/hour speech-grade copy

Speaker splitting (-b): "sentence" gives each sentence to its majority speaker; "word" starts a new line the
moment the speaker changes, even mid-sentence.
"""
import base64
import io
import json
import os
import re
import urllib.error
import urllib.request
from collections import Counter, namedtuple

import av
import click
from faster_whisper import WhisperModel, decode_audio  # PyAV decodes any audio/video container, no ffmpeg needed
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn

OPENROUTER = "https://openrouter.ai/api/v1"
LOCAL_MODEL = "large-v3-turbo"
CLOUD_MODEL = "elevenlabs/scribe-v2"  # word timestamps + diarization
SENTENCE_END = re.compile(r"[.!?…][\"')\]]*$")
# extension -> (container, codec, samples per frame)
CODECS = {".ogg": ("ogg", "libopus", 960), ".opus": ("ogg", "libopus", 960),
          ".mp3": ("mp3", "libmp3lame", 1152), ".m4a": ("ipod", "aac", 1024)}

Word = namedtuple("Word", "start end text spk")
console = Console(stderr=True)  # all UI goes to stderr so stdout stays a clean transcript for pipes


def err(msg):
    console.print(msg, markup=False, highlight=False)


def bar():
    return Progress(
        SpinnerColumn(), TextColumn("{task.description}"), BarColumn(), TaskProgressColumn(),
        TimeElapsedColumn(), TimeRemainingColumn(), console=console,
    )


def stamp(sec: float) -> str:
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def load_audio(path):
    with console.status("Decoding audio..."):
        return decode_audio(path, sampling_rate=16000)


# ---------------------------------------------------------------- compression

def encode_audio(audio, ext=".ogg", kbps=24, label="Compressing") -> bytes:
    """16 kHz mono float audio -> small speech-grade file (24 kbps Opus is ~11 MB/hour)."""
    import numpy as np

    container, codec, n = CODECS[ext]
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with bar() as prog, av.open(buf, "w", format=container) as out:
        task = prog.add_task(label, total=len(pcm))
        stream = out.add_stream(codec, rate=16000)
        stream.layout = "mono"
        stream.bit_rate = kbps * 1000
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16000, frame_size=n)
        for i in range(0, len(pcm), n):
            frame = av.AudioFrame.from_ndarray(pcm[None, i : i + n], format="s16", layout="mono")
            frame.sample_rate = 16000
            for f in resampler.resample(frame):
                out.mux(stream.encode(f))
            prog.update(task, completed=min(i + n, len(pcm)))
        for f in resampler.resample(None):  # flush the last partial frame
            out.mux(stream.encode(f))
        out.mux(stream.encode(None))
    return buf.getvalue()


# ---------------------------------------------------------------- local backend

def local_words(audio, model, language):
    with console.status(f"Loading {model} (first run downloads it)..."):
        segments, info = WhisperModel(model, device="cpu", compute_type="int8").transcribe(
            audio, language=language, vad_filter=True, word_timestamps=True
        )
    err(f"Language: {info.language}, duration: {stamp(info.duration)}")
    words = []
    with bar() as prog:
        task = prog.add_task(f"Transcribing ({model})", total=info.duration)
        for seg in segments:  # lazy generator: this is where the work happens
            words += [Word(w.start, w.end, w.word.strip(), None) for w in seg.words or []]
            prog.update(task, completed=seg.end)
        prog.update(task, completed=info.duration)
    return words


def load_diarizer():
    """Load pyannote up front so a bad/missing HF_TOKEN fails in seconds, not after the transcription."""
    token = os.environ.get("HF_TOKEN")
    if not token or token == "hf_xxx":
        raise click.ClickException("--speakers needs a real HF_TOKEN env var (see --help), or use the `cloud` command.")
    try:
        with console.status("Loading speaker model..."):
            from pyannote.audio import Pipeline

            return Pipeline.from_pretrained("pyannote/speaker-diarization-community-1", token=token)
    except Exception as e:  # bad token, or model terms not accepted yet
        raise click.ClickException(
            f"Could not load the speaker model: {e}\nCheck HF_TOKEN and accept the terms at "
            "https://huggingface.co/pyannote/speaker-diarization-community-1"
        )


def diarize(pipe, audio, num_speakers):
    """Return [(start, end, label)] speaker turns."""
    import torch

    # pass a waveform so pyannote never touches ffmpeg/torchcodec
    with console.status("Identifying speakers (no progress available)..."):
        out = pipe({"waveform": torch.from_numpy(audio)[None], "sample_rate": 16000}, num_speakers=num_speakers)
    ann = getattr(out, "speaker_diarization", out)  # pyannote 4 wraps the Annotation
    return [(t.start, t.end, spk) for t, _, spk in ann.itertracks(yield_label=True)]


def label_words(words, turns):
    # ponytail: linear scan per word (~seconds for a 3h file); bisect over sorted turns if it ever matters
    out = []
    for w in words:
        mid = (w.start + w.end) / 2
        spk = next((s for a, b, s in turns if a <= mid <= b), None)
        if spk is None:  # word fell in a gap between turns: take the nearest one
            spk = min(turns, key=lambda t: min(abs(t[0] - mid), abs(t[1] - mid)))[2]
        out.append(w._replace(spk=spk))
    return out


# ---------------------------------------------------------------- cloud backend

def list_models():
    with urllib.request.urlopen(f"{OPENROUTER}/models?output_modalities=transcription", timeout=30) as r:
        models = json.load(r)["data"]
    click.echo(f"{'MODEL':<52} DIARIZATION")
    for m in sorted(models, key=lambda m: m["id"]):
        diar = "yes" if "diariz" in m.get("description", "").lower() else "-"  # from the model's description
        mark = "  (default)" if m["id"] == CLOUD_MODEL else ""
        click.echo(f"{m['id']:<52} {diar}{mark}")
    err("\nUse with: cloud -m <MODEL>. Diarization column is a hint; unsupported models return an error.")


def post_stt(payload, key):
    req = urllib.request.Request(
        f"{OPENROUTER}/audio/transcriptions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "X-Title": "transcribe_audio.py"},
    )
    try:
        with urllib.request.urlopen(req, timeout=3600) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:500]
        hint = " (audio too large? try a shorter clip)" if e.code == 413 else ""
        raise click.ClickException(f"OpenRouter {e.code}{hint}: {body}")


def cloud_words(audio, model, language, want_speakers):
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise click.ClickException("The cloud command needs the OPENROUTER_API_KEY env var.")
    data = encode_audio(audio, label="Compressing for upload")
    payload = {
        "model": model,
        "input_audio": {"data": base64.b64encode(data).decode(), "format": "ogg"},
        "response_format": "verbose_json",
        "timestamp_granularities": ["word"],
    }
    if language:
        payload["language"] = language
    if want_speakers:
        payload["diarize"] = True
    with console.status(f"Uploading {len(data) / 1e6:.1f} MB and transcribing with {model}..."):
        resp = post_stt(payload, key)

    words = [
        Word(w["start"], w["end"], w["word"].strip(), w.get("speaker_label") or w.get("speaker"))
        for w in resp.get("words") or []
        if w.get("type", "word") == "word"
    ]
    if not words:  # model gave segments only (or just text): each segment acts as one big "word"
        words = [
            Word(s["start"], s["end"], s["text"].strip(), s.get("speaker_label") or s.get("speaker"))
            for s in resp.get("segments") or []
        ] or [Word(0.0, 0.0, resp.get("text", "").strip(), None)]
        err("Note: this model returned no word timestamps; falling back to segment granularity.")
    if want_speakers and all(w.spk is None for w in words):
        err("Warning: model returned no speaker labels. Pick one with diarization (cloud --list-models).")
    return words


# ---------------------------------------------------------------- formatting

def name_speakers(words, names):
    """Relabel raw speaker ids as names (or "Speaker N") in order of first appearance.

    With `names`, only that many speakers exist: words from any extra speaker the model invented are
    reassigned to the speaker just before them (or just after, at the very start).
    """
    order = {}
    for w in words:
        if w.spk is not None:
            order.setdefault(w.spk, len(order))
    spk = [w.spk for w in words]
    if names and len(order) > len(names):
        bad = [s is not None and order[s] >= len(names) for s in spk]
        prev = None
        for i, s in enumerate(spk):
            if bad[i]:
                spk[i] = prev
            elif s is not None:
                prev = s
        nxt = None
        for i in range(len(spk) - 1, -1, -1):
            if bad[i] and spk[i] is None:
                spk[i] = nxt
            elif spk[i] is not None and not bad[i]:
                nxt = spk[i]
    label = lambda s: names[order[s]] if names else f"Speaker {order[s] + 1}"
    return [w._replace(spk=label(s) if s is not None else None) for w, s in zip(words, spk)]


def build_lines(words, by, timestamps, names=None):
    """Group words into [start, speaker, text] units, then render."""
    words = name_speakers(words, names)
    has_spk = any(w.spk for w in words)
    units = []
    if by == "word" and has_spk:  # new unit exactly when the speaker changes
        for w in words:
            if units and units[-1][1] == w.spk:
                units[-1][2] += " " + w.text
            else:
                units.append([w.start, w.spk, w.text])
    else:  # sentence: majority speaker (by word count) decides the whole sentence
        sent = []
        for i, w in enumerate(words):
            sent.append(w)
            if SENTENCE_END.search(w.text) or i == len(words) - 1:
                spk = Counter(x.spk for x in sent).most_common(1)[0][0]
                units.append([sent[0].start, spk, " ".join(x.text for x in sent)])
                sent = []
        if has_spk and not timestamps:  # no timestamps: merge a speaker's consecutive sentences into a paragraph
            merged = []
            for u in units:
                if merged and merged[-1][1] == u[1]:
                    merged[-1][2] += " " + u[2]
                else:
                    merged.append(u)
            units = merged
    return [
        (f"[{stamp(start)}] " if timestamps else "") + (f"{spk}: " if spk else "") + text
        for start, spk, text in units
    ]


def finish(words, speaker_by, timestamps, output, names):
    result = "\n".join(build_lines(words, speaker_by, timestamps, names)) + "\n"
    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(result)
        err(f"Saved to {output}")
    else:
        click.echo(result)


# ---------------------------------------------------------------- CLI

@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def cli():
    """Transcribe audio/video files locally or in the cloud, or compress them."""


@cli.command("audio-compress")
@click.argument("audio_file", type=click.Path(exists=True, dir_okay=False))
@click.option("-o", "--output", required=True, type=click.Path(dir_okay=False),
              help="Output file; extension picks the codec: .ogg/.opus (smallest), .mp3 or .m4a.")
@click.option("--bitrate", type=int, default=24, show_default=True, help="Bitrate in kbps.")
def audio_compress(audio_file, output, bitrate):
    """Save a small speech-grade mono 16 kHz copy of AUDIO_FILE (video tracks are dropped)."""
    ext = os.path.splitext(output)[1].lower()
    if ext not in CODECS:
        raise click.UsageError(f"Output must end in one of {', '.join(CODECS)}.")
    data = encode_audio(load_audio(audio_file), ext, bitrate)
    with open(output, "wb") as f:
        f.write(data)
    err(f"{os.path.getsize(audio_file) / 1e6:.2f} MB -> {len(data) / 1e6:.2f} MB: {output}")


@cli.command()
@click.argument("audio_file", type=click.Path(exists=True, dir_okay=False))
@click.option("-t", "--timestamps", is_flag=True, help="Prefix each line with [HH:MM:SS].")
@click.option("-s", "--speakers", is_flag=True, help="Label speakers.")
@click.option("-b", "--speaker-by", type=click.Choice(["sentence", "word"]), default="sentence", show_default=True,
              help="Assign speakers per sentence (majority speaker) or per word (new line on every change).")
@click.option("-l", "--language", help="Language code (e.g. en). Auto-detected if omitted.")
@click.option("-o", "--output", type=click.Path(dir_okay=False), help="Write transcript here instead of stdout.")
@click.option("--names", callback=lambda ctx, p, v: [n.strip() for n in v.split(",")] if v else None,
              help='Speaker names in order of first appearance, e.g. "Michael,Me,Vicky". Extra detected speakers are folded in.')
@click.option("-n", "--num-speakers", type=int, help="Exact speaker count, if known (improves labels).")
@click.option("-m", "--model", default=LOCAL_MODEL, show_default=True,
              help="Whisper model: tiny/base/small/medium/large-v3/large-v3-turbo.")
def local(audio_file, timestamps, speakers, speaker_by, language, output, names, num_speakers, model):
    """Transcribe on this machine. --speakers needs a Hugging Face token in HF_TOKEN."""
    pipe = load_diarizer() if speakers else None
    num_speakers = num_speakers or (len(names) if names else None)
    audio = load_audio(audio_file)
    words = local_words(audio, model, language)
    if pipe:
        try:
            words = label_words(words, diarize(pipe, audio, num_speakers))
        except Exception as e:  # keep the (expensive) transcript rather than losing it
            err(f"Speaker labelling failed ({e}); writing transcript without speakers.")
    finish(words, speaker_by, timestamps, output, names)


@cli.command()
@click.argument("audio_file", type=click.Path(exists=True, dir_okay=False), required=False)
@click.option("--list-models", "list_models_", is_flag=True, help="List OpenRouter speech-to-text models and exit.")
@click.option("-t", "--timestamps", is_flag=True, help="Prefix each line with [HH:MM:SS].")
@click.option("-s", "--speakers", is_flag=True, help="Label speakers (the model must support diarization).")
@click.option("-b", "--speaker-by", type=click.Choice(["sentence", "word"]), default="sentence", show_default=True,
              help="Assign speakers per sentence (majority speaker) or per word (new line on every change).")
@click.option("-l", "--language", help="Language code (e.g. en). Auto-detected if omitted.")
@click.option("-o", "--output", type=click.Path(dir_okay=False), help="Write transcript here instead of stdout.")
@click.option("--names", callback=lambda ctx, p, v: [n.strip() for n in v.split(",")] if v else None,
              help='Speaker names in order of first appearance, e.g. "Michael,Me,Vicky". Extra detected speakers are folded in.')
@click.option("-m", "--model", default=CLOUD_MODEL, show_default=True, help="OpenRouter model id (see --list-models).")
def cloud(audio_file, list_models_, timestamps, speakers, speaker_by, language, output, names, model):
    """Transcribe via OpenRouter (OPENROUTER_API_KEY). No Hugging Face token needed."""
    if list_models_:
        return list_models()
    if not audio_file:
        raise click.UsageError("Missing AUDIO_FILE (or pass --list-models).")
    words = cloud_words(load_audio(audio_file), model, language, speakers)
    finish(words, speaker_by, timestamps, output, names)


if __name__ == "__main__":
    cli()

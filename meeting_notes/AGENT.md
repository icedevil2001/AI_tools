# Agent Spec: Meeting Recorder & Summarizer (Personal Zoom Notes)

## Overview

This agent records Zoom meetings locally on macOS, transcribes them on-device, and generates structured Markdown reports. It is built for **single-user, personal note-taking** — no sharing, no consent prompts, local storage only. Using python libraries for audio capture, Whisper for transcription, and custom NLP for summarization, it produces a comprehensive meeting summary with action items and decisions.

## Core Workflow

1. **Meeting Detection**
   - Watch for Zoom process start/stop events.
   - Notify user: “Zoom started — begin recording?”
   - Auto-detect input/output devices (mic, speakers).
   - Optionally allow manual audio record or upload (audio/transcript).

2. **Recording**
   - Record input + output streams to `.wav`.
   - Show lightweight tray icon while recording.
   - Store raw audio locally.

3. **Transcription**
   - Run **Whisper-large** on-device for accuracy.
   - Fallback to API if audio >2h or local resources insufficient.
   - Output `.srt` and `.txt` transcripts.

4. **Summarization**
   - Chunk transcript by pauses/topics.
   - Identify:
     - Key updates
     - Assembly/project status
     - Case discussions
     - Technical deep dives
   - Extract **Decisions** and **Action Items** (verb-first, with confidence scoring).
   - Optional risk/blocker detection.
   - Output as structured Markdown + JSON.

5. **Artifact Packaging**
   - Save all results in `~/Documents/MeetingNotes/YYYY-MM-DD_<slug>/`
     - `meeting.md` (structured report)
     - `meeting.srt` (timed transcript)
     - `meeting.wav` (raw audio)
     - `meeting.json` (machine-readable struct)

---

## Output Schema

### Markdown

Follow strict schema:

- `# TL;DR`
- `# Key Topics & Updates` (with subsections)
- `# Decisions`
- `# Action Items` (table)
- `# Risks & Blockers`
- `# Artifacts & Links`
- `# Full Transcript`
- `# Processing Summary`

### JSON (`meeting.json`)

- Meeting metadata (id, title, date, devices, settings)
- Transcript chunks with timestamps & speaker labels
- Summaries, decisions, action items (structured)

---

## Constraints & Assumptions

- **OS**: macOS (MVP)
- **Storage**: Local-only
- **Consent**: Not required (personal notes)
- **Accuracy priority**: High (over speed)
- **Diarization**: Speaker N only (no identity mapping)
- **Integrations**: None (optional export to Notion/local machine later)
- **Mode**: Single-user, private archive

---

## Roles

- **Recorder Agent**  
  Watches Zoom, manages device bindings, records audio.
- **Transcriber Agent**  
  Converts audio to transcript (Whisper-large).
- **Summarizer Agent**  
  Segments transcript → produces summaries, action items, and decisions.
- **Archivist Agent**  
  Packages results into Markdown/JSON, manages folder structure, enforces schema.
- **Operator (You)**  
  Oversees workflows, uploads manual audio/transcripts, reviews outputs.

---

## Roadmap

### Iteration 1 (Capture & Transcribe)

- Zoom detection + recording.
- Whisper transcription.
- Basic Markdown with full transcript only.

### Iteration 2 (Summarization Engine)

- Chunk transcript into topics.
- TL;DR + topic summaries.
- Action item + decision extraction.
- Markdown structured output.

### Iteration 3 (Polish & Upload Mode)

- Manual recording + file upload support.
- Confidence scoring for action items.
- Simple archive search.
- JSON struct output.

---

## Example Use Cases

- **Zoom auto-record** → get full transcript + clean meeting summary.
- **Manual record** (outside Zoom) → capture ad hoc conversations.
- **Upload transcript** → auto-generate structured notes.
- **Upload audio file** → transcribe + summarize like live meeting.

---

## Success Criteria 
- Records and transcribes a 1h Zoom call locally on macOS.
- Outputs Markdown with TL;DR, Key Topics, Decisions, Action Items, Full Transcript.
- Stores artifacts in a local folder with predictable structure.
- Accuracy: comparable to Whisper-large on test set.
- Action items extracted with >70% recall on sample meetings.

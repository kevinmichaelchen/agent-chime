# Requirements

## 1. Overview

Provide audible feedback for agent workflows on macOS when the agent yields or
requires a decision. The system must be low-latency, local-first, and integrate
with `claude`, `codex`, and `opencode`.

## 2. Functional Requirements

### 2.1 Event Detection

- Detect when the agent:
  - finishes and yields control (`AGENT_YIELD`)
  - needs a user decision (`DECISION_REQUIRED`)
  - reports a recoverable error when the CLI exposes an error event
    (`ERROR_RETRY`)
- If a CLI does not expose error events, do not synthesize `ERROR_RETRY`.
- Currently, `ERROR_RETRY` is OpenCode-only via `session.error`.
- Support integration with CLI tooling (`claude`, `codex`, `opencode`).
- Provide a pluggable adapter interface so new CLIs can be added without
  changing core logic.

### 2.2 TTS Broker

- Convert events into short spoken prompts.
- Support per-event templates and short summaries.
- Allow a “silent mode” or “earcon only” mode.

### 2.3 TTS Provider

- Use `mlx-audio` as the unified TTS interface.
- Support multiple models via mlx-audio:
  - `mlx-community/pocket-tts` — default, fastest (~17x real-time)
  - `mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16` — balanced quality/speed
  - `mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16` — highest quality
- All models run locally on Apple Silicon via the MLX framework.
- Model selection is a config option; no separate provider adapters needed.

### 2.4 Audio Rendering

- Play audio immediately (target first audio in <500ms).
- Support streaming playback when available.
- Normalize output format for playback (MP3 or WAV).

### 2.5 Caching

- Cache synthesized audio for repeated prompts.
- Cache key: `(text, voice, speed, provider)`.

### 2.6 Configuration

- Simple local config file (e.g., `agent-chime.json`).
- Configurable voice, rate, and volume.
- Enable/disable per event type.

## 3. Non-Functional Requirements

### 3.1 Performance

- Time-to-first-audio <500ms for local providers.
- Total synthesis <2s for typical prompts.

### 3.2 Reliability

- If TTS fails, fall back to a short earcon.
- Errors must not block the agent output.

### 3.3 Privacy

- All TTS runs locally on-device via mlx-audio.
- No network requests for audio synthesis.

### 3.4 Portability

- macOS only for initial release.
- Apple Silicon optimized.

### 3.5 Accessibility

- Distinct earcons for event types.
- Volume normalization.

## 4. Constraints

- Must integrate with `claude`, `codex`, and `opencode` CLI workflows.
- Must run locally on macOS without external services by default.
- Adapter interface should remain stable even as new tools are added.

## 5. Open Questions

_No open questions at this time. Hook points for each CLI are documented in
design.md section 5._

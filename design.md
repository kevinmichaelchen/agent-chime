# Design

## 1. Goals

- Provide audible cues for `yield` and `decision` events in agentic CLI
  workflows.
- Stay local-first on macOS with low latency.
- Keep integration lightweight and minimally invasive.

## 2. System Overview

### 2.1 Components

- **Event Detectors**: tool-specific adapters that watch agent output and emit
  events.
- **Agent Harness**: a stable adapter interface for CLI tools, with per-tool
  configs and heuristics.
- **TTS Broker**: normalizes events into short, spoken prompts.
- **TTS Provider**: unified mlx-audio interface supporting multiple models
  (PocketTTS, Qwen3-TTS).
- **Audio Renderer**: handles playback and fallback earcons.
- **Cache**: stores audio for repeated prompts.

### 2.2 Data Flow

```
+-----------------+    events     +-------------+    TTS req     +----------------+
| Agent CLI       | ─────────────> | Event       | ─────────────> | TTS Broker     |
| (claude/codex/  |                | Detector    |                | (templates,    |
| opencode)       |                |             |                | policy)        |
+-----------------+                +-------------+                +----------------+
                                                                    |
                                                                    | model.generate()
                                                                    v
                                                          +------------------+
                                                          | mlx-audio        |
                                                          | (pocket-tts /    |
                                                          | Qwen3-TTS)       |
                                                          +------------------+
                                                                    |
                                                                    | audio stream
                                                                    v
                                                          +------------------+
                                                          | Audio Renderer   |
                                                          | (afplay, cache)  |
                                                          +------------------+
```

## 3. Event Model

### 3.1 Event Types

- `AGENT_YIELD`: agent is done and waiting.
- `DECISION_REQUIRED`: agent needs explicit user input.
- `ERROR_RETRY`: recoverable error or interruption.

### 3.2 Event Payload

- `source`: `claude` | `codex` | `opencode`
- `timestamp`: ISO8601
- `summary`: short text to speak
- `context`: optional structured data (e.g., “two options”) for on-screen
  display
- `priority`: `low` | `normal` | `high`

### 3.3 Priorities

- `DECISION_REQUIRED` always high priority.
- `AGENT_YIELD` normal priority, can be coalesced if multiple events occur.
- `ERROR_RETRY` high priority, should preempt lower priority playback.

## 4. Event Detection Strategy

We use each CLI's **native hook/event system** rather than stdout parsing. This
provides reliable event detection without fragile regex patterns.

- **Claude Code**: hooks in `~/.claude/settings.json`
- **Codex**: `notify` config in `~/.codex/config.toml`
- **OpenCode**: plugin system in `.opencode/plugin/`

See **Section 5: CLI Integration** for detailed configuration and JSON payloads.

## 5. CLI Integration

Each supported CLI has its own hook/event system. This section documents how
audio-hooks integrates with each.

### 5.1 Claude Code

Claude Code provides a hooks system configured in `~/.claude/settings.json`.
Hooks receive event data via **stdin as JSON**. See [Claude hooks
docs][claude-hooks-docs].

#### Configuration

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "type": "command",
        "command": "audio-hooks notify --source claude"
      }
    ],
    "Notification": [
      {
        "type": "command",
        "command": "audio-hooks notify --source claude"
      }
    ]
  }
}
```

#### Relevant Events

| Event          | Maps To       | Description                                               |
| -------------- | ------------- | --------------------------------------------------------- |
| `Stop`         | `AGENT_YIELD` | Claude wants to stop working                              |
| `Notification` | `AGENT_YIELD` | Claude is awaiting input                                  |
| `PreToolUse`   | —             | Before tool execution (for `DECISION_REQUIRED` detection) |

#### JSON Payload (stdin)

```json
{
  "session_id": "abc123",
  "transcript_path": "/path/to/transcript.txt",
  "cwd": "/current/working/dir",
  "hook_event_name": "Stop",
  "reason": "Task appears complete"
}
```

#### Key Fields

| Field             | Type      | Description                                            |
| ----------------- | --------- | ------------------------------------------------------ |
| `hook_event_name` | `string`  | Event type: `Stop`, `Notification`, `PreToolUse`, etc. |
| `session_id`      | `string`  | Session identifier                                     |
| `cwd`             | `string`  | Current working directory                              |
| `reason`          | `string?` | Why the event occurred (for `Stop`)                    |
| `tool_name`       | `string?` | Tool name (for `PreToolUse`/`PostToolUse`)             |

#### Detecting `DECISION_REQUIRED`

Claude Code doesn't have a dedicated decision event. Detect via:

1. **PreToolUse** with `tool_name: "AskUserQuestion"` — explicit question
2. **Stop** with `reason` containing decision keywords
3. Pattern matching on `transcript_path` content

### 5.2 Codex

Codex uses a `notify` configuration in `~/.codex/config.toml`. The JSON payload
is passed as a **command-line argument** (not stdin). See [Codex config
docs][codex-config-docs].

#### Configuration

Add to `~/.codex/config.toml`:

```toml
notify = ["audio-hooks", "notify", "--source", "codex"]
```

#### Relevant Events

| Event                 | Maps To       | Description           |
| --------------------- | ------------- | --------------------- |
| `agent-turn-complete` | `AGENT_YIELD` | Agent finished a turn |

> **Note**: `DECISION_REQUIRED` is not yet supported. See [Issue
> #3247][codex-issue-3247] for user approval event support.

#### JSON Payload (CLI argument)

```json
{
  "type": "agent-turn-complete",
  "thread-id": "b5f6c1c2-1111-2222-3333-444455556666",
  "turn-id": "12345",
  "cwd": "/Users/example/project",
  "input-messages": ["Rename foo to bar and update callsites."],
  "last-assistant-message": "Rename complete and verified cargo build succeeds."
}
```

#### Key Fields

| Field                    | Type       | Description                                           |
| ------------------------ | ---------- | ----------------------------------------------------- |
| `type`                   | `string`   | Always `"agent-turn-complete"` (currently only event) |
| `thread-id`              | `string`   | UUID identifying the session                          |
| `turn-id`                | `string`   | Unique identifier for this turn                       |
| `cwd`                    | `string`   | Working directory                                     |
| `input-messages`         | `string[]` | User messages that initiated the turn                 |
| `last-assistant-message` | `string?`  | Final assistant message                               |

#### Parsing in audio-hooks

```python
import sys
import json

# Codex passes JSON as argv[1]
payload = json.loads(sys.argv[1])

if payload["type"] == "agent-turn-complete":
    # Map to AGENT_YIELD
    emit_event("AGENT_YIELD", summary=payload.get("last-assistant-message"))
```

### 5.3 OpenCode

OpenCode uses a plugin system with event hooks. Plugins are
JavaScript/TypeScript modules in `.opencode/plugin/`.

#### Configuration

Create `.opencode/plugin/audio-hooks.js`:

```javascript
export const AudioHooksPlugin = async ({ $ }) => {
  return {
    event: async ({ event }) => {
      if (event.type === "session.idle") {
        await $`audio-hooks notify --source opencode --event AGENT_YIELD`;
      }
      if (event.type === "session.error") {
        await $`audio-hooks notify --source opencode --event ERROR_RETRY`;
      }
      if (event.type === "permission.asked") {
        await $`audio-hooks notify --source opencode --event DECISION_REQUIRED`;
      }
    },
  };
};
```

#### Relevant Events

| Event              | Maps To             | Description            |
| ------------------ | ------------------- | ---------------------- |
| `session.idle`     | `AGENT_YIELD`       | Session completed/idle |
| `session.error`    | `ERROR_RETRY`       | Error occurred         |
| `permission.asked` | `DECISION_REQUIRED` | Permission request     |

See [OpenCode plugin events][opencode-plugins] for the event list. `ERROR_RETRY`
is only available for OpenCode via `session.error`.

#### Alternative: Config-based Hooks

OpenCode also supports experimental config-based hooks in
`.opencode/config.json`:

```json
{
  "experimental": {
    "hook": {
      "session_completed": [
        {
          "command": [
            "audio-hooks",
            "notify",
            "--source",
            "opencode",
            "--event",
            "AGENT_YIELD"
          ],
          "environment": {}
        }
      ]
    }
  }
}
```

`session_completed` is a config-based hook (not an event bus type). It is the
closest equivalent to the `session.idle` event in plugins. See the [OpenCode
config schema][opencode-config-schema].

#### Available Plugin Hooks

| Hook                  | Description                     |
| --------------------- | ------------------------------- |
| `event`               | General event listener          |
| `tool.execute.before` | Before tool execution           |
| `tool.execute.after`  | After tool execution            |
| `permission.ask`      | Permission request interception |

Note: `permission.asked` is an **event type** delivered to the `event` hook (see
[permission events][opencode-permission-events]), while `permission.ask` is a
**plugin hook** used to intercept or auto-respond to permission requests (see
[plugin hooks][opencode-plugin-hooks]).

### 5.4 Event Mapping Summary

| Internal Event      | Claude Code                    | Codex                 | OpenCode           |
| ------------------- | ------------------------------ | --------------------- | ------------------ |
| `AGENT_YIELD`       | `Stop`, `Notification`         | `agent-turn-complete` | `session.idle`     |
| `DECISION_REQUIRED` | `PreToolUse` (AskUserQuestion) | ❌ (Issue #3247)      | `permission.asked` |
| `ERROR_RETRY`       | —                              | —                     | `session.error`    |

### 5.5 Unified Handler

The `audio-hooks notify` command normalizes all inputs:

```python
#!/usr/bin/env python3
import sys
import json
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["notify"])
    parser.add_argument("--source", choices=["claude", "codex", "opencode"])
    parser.add_argument("--event", choices=["AGENT_YIELD", "DECISION_REQUIRED", "ERROR_RETRY"])
    args, unknown = parser.parse_known_args()

    # Determine payload source
    if args.source == "codex" and len(unknown) > 0:
        # Codex: JSON as CLI argument
        payload = json.loads(unknown[0])
        event_type = "AGENT_YIELD"  # Only event type currently
    elif args.source == "claude":
        # Claude: JSON via stdin
        payload = json.load(sys.stdin)
        event_type = map_claude_event(payload["hook_event_name"])
    elif args.source == "opencode":
        # OpenCode: event type passed explicitly
        event_type = args.event
        payload = {}

    # Emit to TTS broker
    emit_audio_event(event_type, args.source, payload)
```

## 6. TTS Broker

### 6.1 Templates

Use short templates to avoid long narration:

- `AGENT_YIELD`: "Ready."
- `DECISION_REQUIRED`: "I need your input."
- `ERROR_RETRY`: "I hit an error. Please review."

### 6.2 Policies

- Max spoken length: 1–2 sentences.
- If summary is long, truncate and add "Check the screen."

## 7. Provider Adapters

### 7.1 Unified Provider: mlx-audio

We use [mlx-audio][mlx-audio] as a single TTS interface. It supports multiple
models through a unified API:

| Model                                         | RTF  | Best For                                   |
| --------------------------------------------- | ---- | ------------------------------------------ |
| `mlx-community/pocket-tts`                    | ~17x | Default — fastest, ideal for short prompts |
| `mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16` | ~6x  | Balanced quality/speed                     |
| `mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16` | ~3x  | Highest quality                            |

Key capabilities:

- Local inference on Apple Silicon (MLX framework)
- Streaming audio generation for low first-audio latency
- Voice cloning from audio samples
- Predefined voices: `alba`, `marius`, `fantine`, `Chelsie`, `Ethan`, etc.

### 7.2 Model Selection Strategy

- **Short prompts** ("Ready.", "I need your input."): Use `pocket-tts` for
  fastest response.
- **Longer summaries**: Use Qwen3 0.6B for better prosody.
- **Fallback**: If model loading fails, play earcon instead.

### 7.3 Provider Interface

```python
from mlx_audio.tts.utils import load_model

class TTSProvider:
    def __init__(self, model: str = "mlx-community/pocket-tts", voice: str = "alba"):
        self.model = load_model(model)
        self.voice = voice
        self.sample_rate = self.model.sample_rate

    def synthesize_stream(self, text: str):
        """Yield audio chunks for immediate playback."""
        for result in self.model.generate(
            text=text,
            voice=self.voice,
            stream=True,
            streaming_interval=0.5
        ):
            yield result.audio

    def synthesize(self, text: str):
        """Return complete audio array."""
        results = list(self.model.generate(text=text, voice=self.voice))
        return results[0].audio if results else None
```

## 8. Audio Rendering

### 8.1 Playback

- Use `afplay` on macOS for MP3/WAV playback.
- For streaming, write chunks to a temp file and begin playback ASAP.

### 8.2 Earcons

- Provide short default earcons for each event type.
- Use earcons as fallback on any TTS error.

## 9. Caching

- LRU cache stored on disk (e.g., `~/.cache/audio-hooks`).
- Keyed by `(text, voice, speed, provider)`.
- Max size configurable.

## 10. Configuration

Example `audio-hooks.json`:

```json
{
  "tts": {
    "model": "mlx-community/pocket-tts",
    "voice": "alba",
    "stream": true,
    "streaming_interval": 0.5
  },
  "volume": 0.8,
  "events": {
    "AGENT_YIELD": { "enabled": true, "mode": "tts" },
    "DECISION_REQUIRED": { "enabled": true, "mode": "tts" },
    "ERROR_RETRY": { "enabled": true, "mode": "earcon" }
  }
}
```

Alternative models can be specified:

```json
{
  "tts": {
    "model": "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16",
    "voice": "Chelsie",
    "stream": true
  }
}
```

## 11. Failure Modes

- TTS provider fails → play earcon, continue.
- Playback fails → log warning, continue.
- Detector misses event → no audio, but no disruption.

## 12. Testing Strategy

- Unit tests for pattern detection and broker templates.
- Integration tests with recorded CLI output logs.
- Manual latency checks on macOS.

## 13. Future Work

- Cross-platform support.
- Speech synthesis personalization (voice cloning).
- UI for configuration and quick toggles.

[mlx-audio]: https://github.com/Blaizzy/mlx-audio
[claude-hooks-docs]: https://code.claude.com/docs/en/hooks
[codex-config-docs]:
  https://github.com/openai/codex/blob/main/codex-rs/core/src/config/mod.rs
[codex-issue-3247]: https://github.com/openai/codex/issues/3247
[opencode-plugins]:
  https://github.com/anomalyco/opencode/blob/dev/packages/web/src/content/docs/plugins.mdx
[opencode-plugin-hooks]:
  https://github.com/anomalyco/opencode/blob/dev/packages/plugin/src/index.ts
[opencode-permission-events]:
  https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/permission/next.ts
[opencode-config-schema]:
  https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/config/config.ts

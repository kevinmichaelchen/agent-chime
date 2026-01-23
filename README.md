# agent-chime

TTS hooks for agentic workflows on macOS. The goal is simple: when your agent
yields or asks for a decision, you hear a short, clear audio cue (TTS or earcon)
while still seeing the full text output.

This project is designed for local-first TTS on Apple Silicon and integrates
with these CLI tools:

- `claude`
- `codex`
- `opencode`

We will build a small event-driven layer that converts agent lifecycle events
into audio prompts.

## Why this exists

- Avoid missing a prompt while your focus is elsewhere.
- Keep the interaction lightweight with short speech (or earcons) instead of
  long narration.
- Remain local-first for privacy and low latency.

## Core ideas

- **Event hooks**: detect `yield` and `decision` moments from agent tools.
- **CLI adapters**: pluggable adapters per CLI tool, easy to extend later.
- **TTS broker**: normalize messages into a compact, spoken prompt.
- **TTS provider**: unified mlx-audio interface for local synthesis.
- **Audio renderer**: plays back audio immediately with minimal delay.

## TTS Provider

We use [mlx-audio][mlx-audio] as a unified TTS interface. It runs locally on
Apple Silicon and supports multiple models:

| Model                                         | Speed          | Use Case                                        |
| --------------------------------------------- | -------------- | ----------------------------------------------- |
| `mlx-community/pocket-tts`                    | ~17x real-time | Default — ultra-fast, perfect for short prompts |
| `mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16` | Fast           | Higher quality, multiple voices                 |
| `mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16` | Moderate       | Best quality, emotion control                   |

All models share the same API (`load_model()` / `generate()`), so switching is
just a config change. PocketTTS and Qwen3-TTS are **not separate libraries** —
both run through mlx-audio.

### Quick Example

```python
from mlx_audio.tts.utils import load_model

model = load_model("mlx-community/pocket-tts")
results = list(model.generate(text="Ready.", voice="alba", stream=True))
```

### Installation

```bash
pip install mlx-audio
```

## Quick Start

Configure your CLI tool to invoke `agent-chime notify` on relevant events.

### Claude Code

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      { "type": "command", "command": "agent-chime notify --source claude" }
    ],
    "Notification": [
      { "type": "command", "command": "agent-chime notify --source claude" }
    ]
  }
}
```

See [Claude hooks docs][claude-hooks-docs].

### Codex

Add to `~/.codex/config.toml`:

```toml
notify = ["agent-chime", "notify", "--source", "codex"]
```

See [Codex config docs][codex-config-docs].

### OpenCode

Create `.opencode/plugin/agent-chime.js`:

```javascript
export const AgentChimePlugin = async ({ $ }) => ({
  event: async ({ event }) => {
    if (event.type === "session.idle")
      await $`agent-chime notify --source opencode --event AGENT_YIELD`;
    if (event.type === "session.error")
      await $`agent-chime notify --source opencode --event ERROR_RETRY`;
    if (event.type === "permission.asked")
      await $`agent-chime notify --source opencode --event DECISION_REQUIRED`;
  },
});
```

See [OpenCode plugin events][opencode-plugins] for the event list. `ERROR_RETRY`
is only available for OpenCode via `session.error`.

## Documents

- `requirements.md` — functional and non-functional requirements
- `design.md` — architecture, event model, and data flow

## Scope (initial)

- macOS only
- English-only prompts
- Short spoken messages (1–2 sentences max)
- Minimal setup and config
- Adapter system for `claude`, `codex`, `opencode`, with a clear path to add
  more

## Non-goals (initial)

- Cross-platform support
- Long-form narration
- UI beyond simple CLI config

## Status

Planning and design phase.

## Implementation

- **Language**: Python 3.10+
- **TTS**: mlx-audio (requires Apple Silicon)
- **Audio**: afplay (macOS built-in)

[mlx-audio]: https://github.com/Blaizzy/mlx-audio
[claude-hooks-docs]: https://code.claude.com/docs/en/hooks
[codex-config-docs]:
  https://github.com/openai/codex/blob/main/codex-rs/core/src/config/mod.rs
[opencode-plugins]:
  https://github.com/anomalyco/opencode/blob/dev/packages/web/src/content/docs/plugins.mdx

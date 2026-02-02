"""Command-line interface for agent-chime."""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from agent_chime.adapters.base import get_adapter
from agent_chime.audio.cache import AudioCache
from agent_chime.audio.renderer import AudioRenderer, PlaybackError
from agent_chime.config import Config, NotificationMode
from agent_chime.events import Event, EventType, Source
from agent_chime.system.detector import SystemDetector
from agent_chime.system.model_selector import ModelSelector, SelectionMode
from agent_chime.tts.broker import TTSBroker
from agent_chime.tts.models import MODELS, QUALITY_ORDER, ModelSpec, ModelTier
from agent_chime.tts.provider import TTSError, TTSProvider

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the CLI."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
    )


def cmd_notify(args: argparse.Namespace) -> int:
    """Handle the notify command."""
    config = Config.load()

    # Parse source
    try:
        source = Source(args.source)
    except ValueError:
        logger.error(f"Unknown source: {args.source}")
        return 1

    # Get adapter and parse input
    adapter = get_adapter(source)

    # Read stdin if not a tty (data is being piped)
    stdin_data = None
    if not sys.stdin.isatty():
        stdin_data = sys.stdin.read()

    # Get additional argv data (anything after known args)
    argv_data = args.extra_args if hasattr(args, "extra_args") else None

    # Parse event from adapter
    event, payload = adapter.parse(
        stdin_data=stdin_data,
        argv_data=argv_data,
        explicit_event=args.event,
    )

    if event is None:
        logger.debug("No event to process")
        return 0

    # Get text to speak via broker
    broker = TTSBroker(config)
    text = broker.get_text_for_event(event, payload)

    # Check if we should play earcon instead
    if broker.should_play_earcon(event):
        return _play_earcon(event.event_type, config)

    if text is None:
        logger.debug("Event is silent or disabled")
        return 0

    # Synthesize and play audio
    return _synthesize_and_play(text, config, args.model)


def _play_earcon(event_type: EventType, config: Config) -> int:
    """Play an earcon for the event type."""
    renderer = AudioRenderer(
        volume=config.volume,
        earcons_dir=config.earcons_dir,
    )

    if renderer.play_earcon(event_type):
        return 0

    logger.warning(f"Could not play earcon for {event_type.value}")
    return 0  # Don't fail on earcon issues


def _synthesize_and_play(text: str, config: Config, model_override: str | None = None) -> int:
    """Synthesize text to speech and play it."""
    # Use cache
    cache = AudioCache(cache_dir=config.cache_dir)

    # Determine model to use
    model_id = model_override or config.tts.model

    # Check cache first
    voice = config.tts.voice or "alba"
    model_for_cache = model_id or "auto"
    cached = cache.get(text, voice, model_for_cache)

    if cached:
        logger.debug("Using cached audio")
        renderer = AudioRenderer(volume=config.volume)
        try:
            renderer.play(cached)
            return 0
        except PlaybackError as e:
            logger.error(f"Playback failed: {e}")
            return 1

    # Synthesize
    try:
        provider = TTSProvider(
            model_id=model_id,
            voice=config.tts.voice,
            stream=config.tts.stream,
            streaming_interval=config.tts.streaming_interval,
        )

        audio = provider.synthesize(text)

        # Cache the result
        actual_model = provider.current_model.model_id if provider.current_model else "unknown"
        cache.put(text, voice, actual_model, audio)

        # Play
        renderer = AudioRenderer(volume=config.volume)
        renderer.play(audio)
        return 0

    except TTSError as e:
        logger.error(f"TTS failed: {e}")
        # Try earcon fallback
        renderer = AudioRenderer(volume=config.volume, earcons_dir=config.earcons_dir)
        if renderer.play_earcon(EventType.AGENT_YIELD):
            return 0
        return 1

    except PlaybackError as e:
        logger.error(f"Playback failed: {e}")
        return 1


def cmd_system_info(args: argparse.Namespace) -> int:
    """Handle the system-info command."""
    detector = SystemDetector()
    info = detector.detect()

    if args.json:
        data = {
            "total_memory_gb": round(info.total_memory_gb, 2),
            "available_memory_gb": round(info.available_memory_gb, 2),
            "metal_available": info.metal_available,
            "chip_name": info.chip_name,
        }
        print(json.dumps(data, indent=2))
    else:
        print(f"Total Memory:     {info.total_memory_gb:.1f} GB")
        print(f"Available Memory: {info.available_memory_gb:.1f} GB")
        print(f"Metal Available:  {'Yes' if info.metal_available else 'No'}")
        if info.chip_name:
            print(f"Chip:             {info.chip_name}")

        # Also show recommended model
        selector = ModelSelector(detector)
        result = selector.select()
        print(f"\nRecommended Model: {result.model.model_id}")
        print(f"  Tier: {result.tier.value}")
        print(f"  Reason: {result.reason}")

    return 0


def cmd_test_tts(args: argparse.Namespace) -> int:
    """Handle the test-tts command."""
    text = args.text or "Hello! Agent chime is working correctly."

    config = Config.load()
    model_id = args.model or config.tts.model

    print(f"Testing TTS with text: '{text}'")
    if model_id:
        print(f"Using model: {model_id}")
    else:
        print("Using auto-selected model")

    try:
        provider = TTSProvider(
            model_id=model_id,
            voice=args.voice or config.tts.voice,
        )

        print("Loading model...")
        audio = provider.synthesize(text)

        if provider.current_model:
            print(f"Model loaded: {provider.current_model.model_id}")

        print(f"Audio size: {len(audio)} bytes")
        print("Playing audio...")

        renderer = AudioRenderer(volume=config.volume)
        renderer.play(audio)

        print("Done!")
        return 0

    except TTSError as e:
        print(f"TTS error: {e}", file=sys.stderr)
        return 1

    except PlaybackError as e:
        print(f"Playback error: {e}", file=sys.stderr)
        return 1


def _get_model_cache_size(model_id: str) -> int | None:
    """Get the disk size of a cached model in bytes, or None if not cached."""
    # HuggingFace cache structure: ~/.cache/huggingface/hub/models--{org}--{name}
    cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
    if not cache_dir.exists():
        return None

    # Convert model_id to cache directory name (e.g., mlx-community/Spark-TTS-0.5B-bf16)
    cache_name = f"models--{model_id.replace('/', '--')}"
    model_cache = cache_dir / cache_name

    if not model_cache.exists():
        return None

    # Calculate total size
    total_size = 0
    for file in model_cache.rglob("*"):
        if file.is_file():
            total_size += file.stat().st_size
    return total_size


def _format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def cmd_models(args: argparse.Namespace) -> int:
    """Handle the models command - list available models and cache status."""
    # Get system info to show which model is recommended
    detector = SystemDetector()
    selector = ModelSelector(detector)
    result = selector.select()
    recommended_tier = result.tier

    if args.json:
        models_data = []
        for tier in QUALITY_ORDER:
            spec = MODELS[tier]
            cache_size = _get_model_cache_size(spec.model_id)
            models_data.append({
                "tier": tier.value,
                "model_id": spec.model_id,
                "memory_gb": spec.estimated_memory_gb,
                "realtime_factor": spec.realtime_factor,
                "requires_metal": spec.requires_metal,
                "description": spec.description,
                "cached": cache_size is not None,
                "cache_size_bytes": cache_size,
                "recommended": tier == recommended_tier,
            })
        print(json.dumps(models_data, indent=2))
        return 0

    # Human-readable output
    print("Available TTS Models")
    print("=" * 60)
    print()

    total_cache_size = 0
    for tier in QUALITY_ORDER:
        spec = MODELS[tier]
        cache_size = _get_model_cache_size(spec.model_id)

        # Header with tier and recommendation marker
        marker = " ★ RECOMMENDED" if tier == recommended_tier else ""
        print(f"[{tier.value.upper()}]{marker}")
        print(f"  Model:   {spec.model_id}")
        print(f"  Memory:  {spec.estimated_memory_gb} GB")
        print(f"  Speed:   {spec.realtime_factor}x realtime")
        print(f"  Metal:   {'Required' if spec.requires_metal else 'Not required'}")
        if spec.description:
            print(f"  Info:    {spec.description}")

        if cache_size is not None:
            print(f"  Cached:  ✓ ({_format_size(cache_size)})")
            total_cache_size += cache_size
        else:
            print("  Cached:  ✗ (not downloaded)")

        print()

    # Summary
    print("-" * 60)
    print(f"Total cache size: {_format_size(total_cache_size)}")
    print(f"Cache location:   ~/.cache/huggingface/hub/")

    return 0


def cmd_config(args: argparse.Namespace) -> int:
    """Handle the config command."""
    config = Config.load()

    if args.validate:
        issues = config.validate()
        if issues:
            print("Configuration issues:")
            for issue in issues:
                print(f"  - {issue}")
            return 1
        print("Configuration is valid")
        return 0

    if args.show:
        print(json.dumps(config.to_dict(), indent=2))
        return 0

    if args.init:
        config_path = Path.home() / ".config" / "agent-chime" / "config.json"
        if config_path.exists() and not args.force:
            print(f"Config already exists at {config_path}")
            print("Use --force to overwrite")
            return 1
        config.save(config_path)
        print(f"Config initialized at {config_path}")
        return 0

    # Default: show config path
    from agent_chime.config import CONFIG_PATHS

    for path in CONFIG_PATHS:
        if path.exists():
            print(f"Config loaded from: {path}")
            return 0

    print("No config file found, using defaults")
    print(f"Create one at: {CONFIG_PATHS[0]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        prog="agent-chime",
        description="Audible notifications for agentic CLI workflows",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # notify command
    notify_parser = subparsers.add_parser(
        "notify",
        help="Process a notification event",
    )
    notify_parser.add_argument(
        "--source",
        choices=["claude", "codex", "opencode"],
        required=True,
        help="Source CLI tool",
    )
    notify_parser.add_argument(
        "--event",
        choices=["AGENT_YIELD", "DECISION_REQUIRED", "ERROR_RETRY"],
        help="Explicit event type (required for opencode)",
    )
    notify_parser.add_argument(
        "--model",
        help="Override TTS model",
    )

    # system-info command
    sysinfo_parser = subparsers.add_parser(
        "system-info",
        help="Show system information and recommended model",
    )
    sysinfo_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    # test-tts command
    test_parser = subparsers.add_parser(
        "test-tts",
        help="Test TTS synthesis and playback",
    )
    test_parser.add_argument(
        "--text",
        help="Text to synthesize (default: test message)",
    )
    test_parser.add_argument(
        "--model",
        help="TTS model to use",
    )
    test_parser.add_argument(
        "--voice",
        help="Voice to use",
    )

    # models command
    models_parser = subparsers.add_parser(
        "models",
        help="List available TTS models and cache status",
    )
    models_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    # config command
    config_parser = subparsers.add_parser(
        "config",
        help="Manage configuration",
    )
    config_parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate the configuration",
    )
    config_parser.add_argument(
        "--show",
        action="store_true",
        help="Show current configuration",
    )
    config_parser.add_argument(
        "--init",
        action="store_true",
        help="Initialize default configuration file",
    )
    config_parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite existing config",
    )

    # Parse known args to allow extra args for codex
    args, extra = parser.parse_known_args(argv)
    args.extra_args = extra

    setup_logging(args.verbose)

    if args.command is None:
        parser.print_help()
        return 0

    commands = {
        "notify": cmd_notify,
        "system-info": cmd_system_info,
        "test-tts": cmd_test_tts,
        "models": cmd_models,
        "config": cmd_config,
    }

    cmd_func = commands.get(args.command)
    if cmd_func is None:
        parser.print_help()
        return 1

    return cmd_func(args)


if __name__ == "__main__":
    sys.exit(main())

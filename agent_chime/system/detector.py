"""System resource detection for macOS Apple Silicon."""

import logging
import subprocess
from dataclasses import dataclass

import psutil

logger = logging.getLogger(__name__)


@dataclass
class SystemInfo:
    """System resource information."""

    total_memory_gb: float
    available_memory_gb: float
    metal_available: bool
    chip_name: str | None = None

    def __str__(self) -> str:
        metal_status = "available" if self.metal_available else "not available"
        chip_info = f" ({self.chip_name})" if self.chip_name else ""
        return (
            f"Memory: {self.available_memory_gb:.1f}GB available / "
            f"{self.total_memory_gb:.1f}GB total, "
            f"Metal: {metal_status}{chip_info}"
        )


class SystemDetector:
    """Detects system resources for model selection."""

    def detect(self) -> SystemInfo:
        """Detect current system resources."""
        return SystemInfo(
            total_memory_gb=self._get_total_memory(),
            available_memory_gb=self._get_available_memory(),
            metal_available=self._check_metal(),
            chip_name=self._get_chip_name(),
        )

    def _get_total_memory(self) -> float:
        """Get total system memory in GB using sysctl."""
        try:
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True,
                text=True,
                check=True,
            )
            bytes_total = int(result.stdout.strip())
            return bytes_total / (1024**3)
        except (subprocess.CalledProcessError, ValueError) as e:
            logger.warning(f"Failed to get total memory via sysctl: {e}")
            # Fallback to psutil
            return psutil.virtual_memory().total / (1024**3)

    def _get_available_memory(self) -> float:
        """Get available system memory in GB using psutil."""
        return psutil.virtual_memory().available / (1024**3)

    def _check_metal(self) -> bool:
        """Check if Metal GPU acceleration is available via MLX."""
        try:
            import mlx.core as mx

            return mx.metal.is_available()
        except ImportError:
            logger.warning("MLX not installed, cannot check Metal availability")
            return False
        except Exception as e:
            logger.warning(f"Failed to check Metal availability: {e}")
            return False

    def _get_chip_name(self) -> str | None:
        """Get the Apple Silicon chip name."""
        try:
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            # Try alternative for Apple Silicon
            try:
                result = subprocess.run(
                    ["system_profiler", "SPHardwareDataType"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                for line in result.stdout.splitlines():
                    if "Chip" in line:
                        return line.split(":")[-1].strip()
            except subprocess.CalledProcessError:
                pass
        return None

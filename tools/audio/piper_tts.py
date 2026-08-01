"""Piper local text-to-speech provider tool."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import wave
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)


class PiperTTS(BaseTool):
    name = "piper_tts"
    version = "0.1.0"
    tier = ToolTier.VOICE
    capability = "tts"
    provider = "piper"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    dependencies = ["python:piper"]
    install_instructions = (
        "Install the Piper Python package (required for synthesis):\n"
        "  pip install piper-tts\n"
        "Optional CLI (voice download only):\n"
        "  https://github.com/rhasspy/piper/releases\n"
        "Download a voice model (example English):\n"
        "  python -m piper.download_voices en_US-lessac-medium\n"
        "Chinese example:\n"
        "  python -m piper.download_voices zh_CN-huayan-medium"
    )
    agent_skills = ["text-to-speech"]

    capabilities = [
        "text_to_speech",
        "offline_generation",
    ]
    supports = {
        "voice_cloning": False,
        "multilingual": False,
        "offline": True,
        "native_audio": True,
    }
    best_for = [
        "offline narration fallback",
        "privacy-sensitive local-only workflows",
    ]
    not_good_for = [
        "best-in-class expressive voice quality",
        "voice clone matching",
    ]

    input_schema = {
        "type": "object",
        "required": ["text"],
        "properties": {
            "text": {"type": "string"},
            "model": {
                "type": "string",
                "default": "en_US-lessac-medium",
            },
            "speaker_id": {
                "type": "integer",
                "default": 0,
            },
            "length_scale": {
                "type": "number",
                "default": 1.0,
            },
            "sentence_silence": {
                "type": "number",
                "default": 0.3,
            },
            "output_path": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=2, ram_mb=512, vram_mb=0, disk_mb=200, network_required=False
    )
    retry_policy = RetryPolicy(max_retries=1, retryable_errors=[])
    idempotency_key_fields = ["text", "model", "speaker_id", "length_scale"]
    side_effects = ["writes audio file to output_path"]
    user_visible_verification = ["Listen to generated audio for intelligibility"]

    def get_status(self) -> ToolStatus:
        # Generation uses the Python API (`from piper import PiperVoice`), not
        # the `piper` CLI. A CLI-only install must not read as available.
        return super().get_status()

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        if self.get_status() != ToolStatus.AVAILABLE:
            return ToolResult(success=False, error="Piper TTS not available. " + self.install_instructions)

        start = time.time()
        try:
            result = self._generate(inputs)
        except Exception as exc:
            return ToolResult(success=False, error=f"Local TTS generation failed: {exc}")

        result.duration_seconds = round(time.time() - start, 2)
        return result

    def _models_dir(self) -> Path:
        """Directory where downloaded .onnx voices live."""
        env = os.environ.get("PIPER_DATA_DIR") or os.environ.get("PIPER_MODEL_DIR")
        if env:
            return Path(env)
        return Path.home() / ".local" / "share" / "piper"

    def _resolve_model(self, model: str) -> Path:
        """Resolve a model name (e.g. ``zh_CN-huayan-medium``) or path to a
        concrete ``.onnx`` file, downloading the voice if it is missing."""
        p = Path(model)
        if p.suffix == ".onnx" and p.exists():
            return p

        models_dir = self._models_dir()
        candidate = models_dir / f"{model}.onnx"
        if candidate.exists():
            return candidate
        for alt in (Path.cwd() / f"{model}.onnx", Path.home() / f"{model}.onnx"):
            if alt.exists():
                return alt

        # Not present locally — download the voice into the models dir.
        models_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["python", "-m", "piper.download_voices", model, "--download-dir", str(models_dir)],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if candidate.exists():
            return candidate
        raise FileNotFoundError(
            f"Could not resolve or download Piper voice model '{model}'. "
            f"Looked in {models_dir}."
        )

    def _generate(self, inputs: dict[str, Any]) -> ToolResult:
        output_path = Path(inputs.get("output_path", "tts_output.wav"))
        output_path.parent.mkdir(parents=True, exist_ok=True)

        model = inputs.get("model", "en_US-lessac-medium")
        model_path = self._resolve_model(model)

        # Use the Python API rather than the `piper` CLI: the 1.4.x CLI WAV
        # writer fails ("# channels not specified") on Python 3.14. The API's
        # synthesize_wav sets the WAV header itself and is the reliable path.
        from piper import PiperVoice, SynthesisConfig

        voice = PiperVoice.load(str(model_path))
        syn_config = SynthesisConfig(
            speaker_id=int(inputs.get("speaker_id", 0)) or None,
            length_scale=float(inputs.get("length_scale", 1.0)),
        )
        with wave.open(str(output_path), "wb") as wf:
            voice.synthesize_wav(inputs["text"], wf, syn_config=syn_config)

        if not output_path.exists() or output_path.stat().st_size == 0:
            return ToolResult(success=False, error=f"Piper output file missing or empty: {output_path}")

        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "model": inputs.get("model", "en_US-lessac-medium"),
                "speaker_id": inputs.get("speaker_id", 0),
                "text_length": len(inputs["text"]),
                "output": str(output_path),
                "format": "wav",
            },
            artifacts=[str(output_path)],
            model=inputs.get("model", "en_US-lessac-medium"),
        )

"""Video downloader tool wrapping yt-dlp.

Downloads video, audio, or subtitles from YouTube, Shorts, Instagram Reels,
TikTok, and 1000+ other sites. Designed for reference video analysis — downloads
at analysis quality (720p), not production quality.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from plugins.openmontage.tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    ToolResult,
    ToolStability,
    ToolStatus,
    ToolTier,
    ToolRuntime,
)


class VideoDownloader(BaseTool):
    name = "video_downloader"
    version = "0.1.0"
    tier = ToolTier.SOURCE
    capability = "source_ingest"
    provider = "yt-dlp"
    stability = ToolStability.PRODUCTION
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    dependencies = ["python:yt_dlp"]
    install_instructions = (
        "Install yt-dlp: pip install yt-dlp\n"
        "Douyin links download via VidDown (viddown.cn) by default (VIDDOWN_ENABLED=1). "
        "Set VIDDOWN_ENABLED=0 to use yt-dlp with browser cookies instead.\n"
        "For YouTube support, also install Deno (JS runtime): "
        "https://deno.land/#installation\n"
        "Without Deno, YouTube downloads may fail but other platforms still work."
    )
    agent_skills = ["video-download"]

    capabilities = [
        "download_video",
        "download_audio",
        "download_subtitles",
        "extract_metadata",
    ]

    best_for = [
        "downloading reference video from URL",
        "extracting audio from online video",
        "downloading subtitles from YouTube",
        "getting video metadata without downloading",
    ]

    not_good_for = [
        "downloading entire playlists",
        "downloading DRM-protected content",
    ]

    input_schema = {
        "type": "object",
        "required": ["url", "output_dir"],
        "properties": {
            "url": {"type": "string", "description": "Video URL to download"},
            "output_dir": {"type": "string", "description": "Directory for downloaded files"},
            "format": {
                "type": "string",
                "enum": ["video", "audio_only", "subtitles_only", "metadata_only"],
                "default": "video",
                "description": "What to download",
            },
            "max_resolution": {
                "type": "string",
                "enum": ["360p", "480p", "720p", "1080p"],
                "default": "720p",
                "description": "Maximum video resolution (for analysis, 720p is sufficient)",
            },
            "max_duration_seconds": {
                "type": "integer",
                "default": 600,
                "description": "Reject videos longer than this (safety limit)",
            },
        },
    }

    output_schema = {
        "type": "object",
        "properties": {
            "video_path": {"type": ["string", "null"]},
            "audio_path": {"type": ["string", "null"]},
            "subtitle_path": {"type": ["string", "null"]},
            "metadata": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "duration": {"type": "number"},
                    "uploader": {"type": "string"},
                    "upload_date": {"type": "string"},
                    "description": {"type": "string"},
                    "view_count": {"type": "integer"},
                    "like_count": {"type": "integer"},
                },
            },
            "platform": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=2000,
        network_required=True,
    )
    idempotency_key_fields = ["url", "format", "max_resolution"]
    side_effects = ["downloads media files to output_dir"]
    resume_support_value = "from_start"
    user_visible_verification = [
        "Check downloaded file plays correctly",
        "Verify resolution matches requested max",
    ]

    # --- Resolution mapping ---
    _RES_MAP = {
        "360p": 360,
        "480p": 480,
        "720p": 720,
        "1080p": 1080,
    }

    def _ydl_opts(self, **extra: Any) -> dict[str, Any]:
        """Base yt-dlp options including optional cookie injection."""
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }
        browser = os.environ.get("YTDLP_COOKIES_FROM_BROWSER", "").strip()
        if browser:
            opts["cookiesfrombrowser"] = (browser,)
        cookie_file = os.environ.get("YTDLP_COOKIE_FILE", "").strip()
        if cookie_file and Path(cookie_file).is_file():
            opts["cookiefile"] = cookie_file
        opts.update(extra)
        return opts

    def _detect_platform(self, url: str) -> str:
        """Detect platform from URL."""
        url_lower = url.lower()
        if "douyin.com" in url_lower or "iesdouyin.com" in url_lower:
            return "douyin"
        if "youtube.com/shorts" in url_lower or "youtu.be" in url_lower and "/shorts" in url_lower:
            return "shorts"
        if "youtube.com" in url_lower or "youtu.be" in url_lower:
            return "youtube"
        if "instagram.com" in url_lower:
            return "instagram"
        if "tiktok.com" in url_lower:
            return "tiktok"
        if "bilibili.com" in url_lower or "b23.tv" in url_lower:
            return "bilibili"
        if "vimeo.com" in url_lower:
            return "vimeo"
        if "twitter.com" in url_lower or "x.com" in url_lower:
            return "twitter"
        return "other_url"

    def _douyin_error_hint(self) -> str:
        return (
            "Douyin link download failed. Options: "
            "(1) upload the video locally instead of using a link; "
            "(2) retry later — VidDown (viddown.cn) may be temporarily unavailable; "
            "(3) set VIDDOWN_ENABLED=0 and configure yt-dlp cookies "
            "(YTDLP_COOKIES_FROM_BROWSER=chrome or YTDLP_COOKIE_FILE=path)"
        )

    def _resolution_height(self, max_res: str) -> int:
        return self._RES_MAP.get(max_res, 720)

    def _save_viddown_video(
        self,
        output_dir: Path,
        blob: bytes,
    ) -> tuple[str | None, str | None]:
        video_out = output_dir / "reference_video.mp4"
        video_out.write_bytes(blob)
        video_path = str(video_out)
        audio_path = None
        audio_out = output_dir / "reference_audio.wav"
        try:
            audio_cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-vn",
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                str(audio_out),
            ]
            self.run_command(audio_cmd, timeout=120)
            if audio_out.exists():
                audio_path = str(audio_out)
        except Exception:
            pass
        return video_path, audio_path

    def _download_douyin_via_viddown(
        self,
        url: str,
        output_dir: Path,
        *,
        max_res: str,
        dl_format: str,
    ) -> ToolResult:
        from plugins.openmontage.tools.analysis.viddown_client import VidDownError, fetch_douyin_via_viddown

        start = time.time()
        try:
            payload = fetch_douyin_via_viddown(
                url,
                max_height=self._resolution_height(max_res),
            )
        except VidDownError as exc:
            return ToolResult(
                success=False,
                error=f"{exc}\n\n{self._douyin_error_hint()}",
                data={"metadata": {"error": str(exc)}, "platform": "douyin", "provider": "viddown"},
                duration_seconds=round(time.time() - start, 2),
            )

        metadata = payload.get("metadata") or {}
        if dl_format == "metadata_only":
            return ToolResult(
                success=True,
                data={
                    "video_path": None,
                    "audio_path": None,
                    "subtitle_path": None,
                    "metadata": metadata,
                    "platform": "douyin",
                    "provider": "viddown",
                    "viddown_task_id": payload.get("task_id"),
                },
                duration_seconds=round(time.time() - start, 2),
            )

        video_path, audio_path = self._save_viddown_video(
            output_dir,
            payload["video_bytes"],
        )
        artifacts = [p for p in [video_path, audio_path] if p]
        return ToolResult(
            success=True,
            data={
                "video_path": video_path,
                "audio_path": audio_path,
                "subtitle_path": None,
                "metadata": metadata,
                "platform": "douyin",
                "provider": "viddown",
                "viddown_task_id": payload.get("task_id"),
            },
            artifacts=artifacts,
            duration_seconds=round(time.time() - start, 2),
        )

    def _metadata_error_message(self, metadata: dict[str, Any], platform: str) -> str | None:
        err = str(metadata.get("error") or "").strip()
        if not err:
            return None
        if platform == "douyin" or "Douyin" in err or "cookies" in err.lower():
            return f"{err}\n\n{self._douyin_error_hint()}"
        return err

    def _extract_metadata(self, url: str) -> dict:
        """Extract metadata without downloading."""
        import yt_dlp

        ydl_opts = self._ydl_opts(skip_download=True)
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info is None:
                    return {"error": "No info extracted", "title": "", "duration": 0}
                return {
                    "title": info.get("title", ""),
                    "duration": info.get("duration", 0),
                    "uploader": info.get("uploader", info.get("channel", "")),
                    "upload_date": info.get("upload_date", ""),
                    "description": (info.get("description", "") or "")[:500],
                    "view_count": info.get("view_count", 0),
                    "like_count": info.get("like_count", 0),
                    "resolution": f"{info.get('width', 0)}x{info.get('height', 0)}",
                    "fps": info.get("fps", 0),
                }
        except Exception as e:
            return {"error": str(e), "title": "", "duration": 0}

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        url = inputs["url"]
        output_dir = Path(inputs["output_dir"])
        dl_format = inputs.get("format", "video")
        max_res = inputs.get("max_resolution", "720p")
        max_duration = inputs.get("max_duration_seconds", 600)

        output_dir.mkdir(parents=True, exist_ok=True)
        platform = self._detect_platform(url)
        start = time.time()

        if platform == "douyin":
            from plugins.openmontage.tools.analysis.viddown_client import viddown_enabled

            if viddown_enabled():
                viddown_result = self._download_douyin_via_viddown(
                    url,
                    output_dir,
                    max_res=max_res,
                    dl_format=dl_format,
                )
                duration = (viddown_result.data or {}).get("metadata", {}).get("duration", 0)
                if viddown_result.success and duration and duration > max_duration:
                    return ToolResult(
                        success=False,
                        error=(
                            f"Video is {duration}s, exceeds max_duration_seconds={max_duration}. "
                            f"Increase the limit or use a shorter video."
                        ),
                        data=viddown_result.data,
                    )
                return viddown_result

        # Step 1: Always get metadata first (non-Douyin, or Douyin with VidDown disabled)
        metadata = self._extract_metadata(url)
        meta_err = self._metadata_error_message(metadata, platform)
        if meta_err:
            return ToolResult(
                success=False,
                error=meta_err,
                data={"metadata": metadata, "platform": platform},
            )

        # Check duration limit
        duration = metadata.get("duration", 0)
        if duration and duration > max_duration:
            return ToolResult(
                success=False,
                error=(
                    f"Video is {duration}s, exceeds max_duration_seconds={max_duration}. "
                    f"Increase the limit or use a shorter video."
                ),
                data={"metadata": metadata, "platform": platform},
            )

        if dl_format == "metadata_only":
            return ToolResult(
                success=True,
                data={
                    "video_path": None,
                    "audio_path": None,
                    "subtitle_path": None,
                    "metadata": metadata,
                    "platform": platform,
                },
                duration_seconds=round(time.time() - start, 2),
            )

        video_path = None
        audio_path = None
        subtitle_path = None

        try:
            if dl_format == "video":
                video_path, audio_path = self._download_video(
                    url, output_dir, max_res
                )
            elif dl_format == "audio_only":
                audio_path = self._download_audio(url, output_dir)
            elif dl_format == "subtitles_only":
                subtitle_path = self._download_subtitles(url, output_dir)
        except Exception as e:
            elapsed = time.time() - start
            return ToolResult(
                success=False,
                error=f"Download failed: {e}",
                data={"metadata": metadata, "platform": platform},
                duration_seconds=round(elapsed, 2),
            )

        elapsed = time.time() - start
        artifacts = [p for p in [video_path, audio_path, subtitle_path] if p]

        return ToolResult(
            success=True,
            data={
                "video_path": video_path,
                "audio_path": audio_path,
                "subtitle_path": subtitle_path,
                "metadata": metadata,
                "platform": platform,
            },
            artifacts=artifacts,
            duration_seconds=round(elapsed, 2),
        )

    def _download_video(
        self, url: str, output_dir: Path, max_res: str
    ) -> tuple[str | None, str | None]:
        """Download video + extract audio track."""
        import yt_dlp

        height = self._RES_MAP.get(max_res, 720)
        video_out = str(output_dir / "reference_video.%(ext)s")

        ydl_opts = self._ydl_opts(
            format=f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best",
            merge_output_format="mp4",
            outtmpl=video_out,
        )
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Find the downloaded video file
        video_path = self._find_downloaded(output_dir, "reference_video", ["mp4", "mkv", "webm"])

        # Extract audio separately for transcription
        audio_path = None
        if video_path:
            audio_out = output_dir / "reference_audio.wav"
            try:
                audio_cmd = [
                    "ffmpeg", "-y",
                    "-i", video_path,
                    "-vn",
                    "-acodec", "pcm_s16le",
                    "-ar", "16000",
                    "-ac", "1",
                    str(audio_out),
                ]
                self.run_command(audio_cmd, timeout=120)
                if audio_out.exists():
                    audio_path = str(audio_out)
            except Exception:
                pass  # Audio extraction is optional

        return video_path, audio_path

    def _download_audio(self, url: str, output_dir: Path) -> str | None:
        """Download audio only."""
        import yt_dlp

        audio_out = str(output_dir / "reference_audio.%(ext)s")
        ydl_opts = self._ydl_opts(
            format="bestaudio/best",
            postprocessors=[{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "0",
            }],
            outtmpl=audio_out,
        )
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return self._find_downloaded(output_dir, "reference_audio", ["wav", "mp3", "m4a", "opus"])

    def _download_subtitles(self, url: str, output_dir: Path) -> str | None:
        """Download subtitles only."""
        import yt_dlp

        sub_out = str(output_dir / "reference_subs.%(ext)s")
        ydl_opts = self._ydl_opts(
            writesubtitles=True,
            writeautomaticsub=True,
            subtitleslangs=["en"],
            subtitlesformat="srt",
            skip_download=True,
            outtmpl=sub_out,
        )
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception:
            pass
        return self._find_downloaded(output_dir, "reference_subs", ["srt", "vtt", "ass"])

    def _find_downloaded(
        self, output_dir: Path, prefix: str, extensions: list[str]
    ) -> str | None:
        """Find a downloaded file by prefix and possible extensions."""
        for ext in extensions:
            candidates = list(output_dir.glob(f"{prefix}*.{ext}"))
            if candidates:
                return str(candidates[0])
        return None

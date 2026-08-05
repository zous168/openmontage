"""Shared constants for Hermes Agent.

Import-safe module with no dependencies — can be imported from anywhere
without risk of circular imports.
"""

import os
import sys
import sysconfig
from contextvars import ContextVar, Token
from pathlib import Path


MARKETING_HUB_DATA_DIRNAME = ".marketing_hub"
_UNSET = object()
_HERMES_HOME_OVERRIDE: ContextVar[str | object] = ContextVar(
    "_HERMES_HOME_OVERRIDE", default=_UNSET
)


def set_hermes_home_override(path: str | Path | None) -> Token:
    """Set a context-local Hermes home override and return its reset token.

    This is for in-process, per-task scoping.  It deliberately does not mutate
    ``os.environ`` because that is shared by every thread in the process.
    """
    value: str | object = _UNSET if path is None else str(path)
    return _HERMES_HOME_OVERRIDE.set(value)


def reset_hermes_home_override(token: Token) -> None:
    """Restore the previous context-local Hermes home override."""
    _HERMES_HOME_OVERRIDE.reset(token)


def get_hermes_home_override() -> str | None:
    """Return the active context-local Hermes home override, if any."""
    override = _HERMES_HOME_OVERRIDE.get()
    if override is _UNSET or not override:
        return None
    return str(override)


def _get_platform_default_hermes_home() -> Path:
    """无 runtime_paths 时的兜底 Agent 数据根."""
    try:
        from runtime_paths import resolve_repo_root

        return resolve_repo_root() / ".data"
    except ImportError:
        pass
    return Path.home() / ".marketing_hub"

def _hub_data_dir_from_env() -> Path | None:
    raw = os.environ.get("HUB_DATA_DIR", "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def _agent_base_dir() -> Path:
    """Agent 数据根（``HUB_DATA_DIR``）."""
    explicit = _hub_data_dir_from_env()
    if explicit is not None:
        return explicit
    try:
        from runtime_paths import resolve_hermes_data_dir

        return resolve_hermes_data_dir()
    except ImportError:
        pass
    try:
        from src.runtime_paths import resolve_hermes_data_dir

        return resolve_hermes_data_dir()
    except ImportError:
        pass
    return _get_platform_default_hermes_home()


def _active_profile_name() -> str:
    """``HERMES_PROFILE`` 或 ``active_profile`` 文件中的 profile 名."""
    profile = os.environ.get("HERMES_PROFILE", "").strip()
    if profile:
        return profile
    active_path = _agent_base_dir() / "active_profile"
    if not active_path.exists():
        return ""
    try:
        return active_path.read_text().strip()
    except (UnicodeDecodeError, OSError):
        return ""


def _profile_agent_dir(base: Path, profile_name: str) -> Path:
    """将 profile 名映射为数据目录（``profiles/<name>`` 或根）."""
    name = (profile_name or "").strip()
    if not name or name.casefold() == "default":
        return base
    return base / "profiles" / name.strip().lower()


def get_hermes_home() -> Path:
    """Return the Agent data directory.

    ``HUB_DATA_DIR``（+ ``HERMES_PROFILE`` 子目录）。不读取 ``HERMES_HOME`` 环境变量。
    """
    override = get_hermes_home_override()
    if override:
        return Path(override)

    base = _agent_base_dir()
    return _profile_agent_dir(base, _active_profile_name())


def get_default_hermes_root() -> Path:
    """Profile 列表等操作的根目录（default profile 的数据根）."""
    return _agent_base_dir()


def get_hub_logs_dir() -> Path:
    """运行时日志目录：``{data_root}/logs``（dev ``.data/logs``，打包 ``data/logs``）."""
    return get_default_hermes_root() / "logs"


def get_agent_workspace_dir() -> Path:
    """Agent 的默认工作目录：``{profile 数据根}/workspace``。

    会话没有显式 cwd 时的落点。刻意不取进程 cwd —— gateway 由别处拉起，它的启动
    目录不代表用户想让 agent 干活的地方。开发机上那就是源码仓库根，于是仓库的
    ``AGENTS.md`` / ``CLAUDE.md`` 会被注进每一轮 prompt，agent 的相对路径操作也
    落进源码树。跟着 profile 走则换机器、换 profile 都自洽。

    目录按需创建：调用方（会话 cwd 解析）只接受真实存在的目录，不存在就会退回
    进程 cwd，正是这里要避免的。
    """
    workspace = get_hermes_home() / "workspace"
    try:
        workspace.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return workspace


def _get_packaged_data_dir(name: str) -> Path | None:
    """Return an installed data-files directory if one exists.

    Used to discover bundled skills/optional-skills when Hermes is installed
    from a wheel that emitted them via setuptools data_files.
    """
    candidates = []
    for scheme in ("data", "purelib", "platlib"):
        raw = sysconfig.get_path(scheme)
        if raw:
            candidates.append(Path(raw) / name)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def get_optional_skills_dir(default: Path | None = None) -> Path:
    """Return the optional-skills directory, honoring package-manager wrappers.

    Packaged installs may ship ``optional-skills`` outside the Python package
    tree and expose it via ``HERMES_OPTIONAL_SKILLS``.
    """
    override = os.getenv("HERMES_OPTIONAL_SKILLS", "").strip()
    if override:
        return Path(override)
    packaged = _get_packaged_data_dir("optional-skills")
    if packaged is not None:
        return packaged
    if default is not None:
        return default
    return get_hermes_home() / "optional-skills"


def get_optional_mcps_dir(default: Path | None = None) -> Path:
    """Return the optional-mcps directory, honoring package-manager wrappers.

    Mirrors :func:`get_optional_skills_dir` for the MCP catalog (Nous-approved
    Model Context Protocol servers shipped with the repo but disabled by
    default). Packaged installs may ship ``optional-mcps`` outside the Python
    package tree and expose it via ``HERMES_OPTIONAL_MCPS``.
    """
    override = os.getenv("HERMES_OPTIONAL_MCPS", "").strip()
    if override:
        return Path(override)
    packaged = _get_packaged_data_dir("optional-mcps")
    if packaged is not None:
        return packaged
    if default is not None:
        return default
    return get_hermes_home() / "optional-mcps"


def get_bundled_skills_dir(default: Path | None = None) -> Path:
    """Return the bundled skills directory for source and packaged installs.

    Resolution order:
        1. ``HERMES_BUNDLED_SKILLS`` env var (Nix wrapper / explicit override)
        2. Wheel-installed ``<sysconfig data>/skills`` (pip install path)
        3. Caller-supplied ``default`` (typically the source-checkout path)
        4. ``<HERMES_HOME>/skills`` last-resort
    """
    override = os.getenv("HERMES_BUNDLED_SKILLS", "").strip()
    if override:
        return Path(override)
    packaged = _get_packaged_data_dir("skills")
    if packaged is not None:
        return packaged
    if default is not None:
        return default
    return get_hermes_home() / "skills"


def get_hermes_dir(new_subpath: str, old_name: str) -> Path:
    """Resolve a Hermes subdirectory with backward compatibility.

    New installs get the consolidated layout (e.g. ``cache/images``).
    Existing installs that already have the old path (e.g. ``image_cache``)
    keep using it — no migration required.

    Args:
        new_subpath: Preferred path relative to HERMES_HOME (e.g. ``"cache/images"``).
        old_name: Legacy path relative to HERMES_HOME (e.g. ``"image_cache"``).

    Returns:
        Absolute ``Path`` — old location if it exists on disk, otherwise the new one.
    """
    home = get_hermes_home()
    old_path = home / old_name
    if old_path.exists():
        return old_path
    return home / new_subpath


def display_hermes_home() -> str:
    """当前 Agent 数据根的用户可见路径（文案用）。

    MxAI 实际落点由 ``HUB_DATA_DIR`` / 安装目录 ``data`` 决定，例如：
    ``%LOCALAPPDATA%/MxAI*/data``、仓库 ``.data``；**不要**再写死
    ``~/.marketing_hub``（那只是无 runtime 时的历史兜底名）。

    在用户主目录下时用 ``~/`` 缩写，否则返回绝对路径。
    代码取路径用 :func:`get_hermes_home` / :func:`get_default_hermes_root`。
    """
    home = get_hermes_home()
    try:
        return "~/" + str(home.relative_to(Path.home())).replace("\\", "/")
    except ValueError:
        return str(home)


def display_hermes_env_path() -> str:
    """用户可见的 ``{数据根}/.env`` 路径（文案用）。"""
    return f"{display_hermes_home()}/.env"


def secure_parent_dir(path: Path) -> None:
    """Chmod ``0o700`` on the parent directory of *path*, but only if safe.

    Refuses to chmod ``/`` or any top-level directory (resolved parent with
    fewer than 3 parts, i.e. ``/`` or any direct child like ``/usr``) to
    prevent catastrophic host bricking when ``HERMES_HOME`` or other path
    env vars resolve to an unexpected location.

    See https://github.com/NousResearch/hermes-agent/issues/25821.
    """
    parent = path.parent.resolve()
    # Refuse root and its direct children (/usr, /home, /var, /tmp, …).
    if parent == Path("/") or len(parent.parts) < 3:
        return
    try:
        os.chmod(parent, 0o700)
    except OSError:
        pass


def get_subprocess_home() -> str | None:
    """Return a per-profile HOME directory for subprocesses, or None.

    When ``{HERMES_HOME}/home/`` exists on disk, subprocesses should use it
    as ``HOME`` so system tools (git, ssh, gh, npm …) write their configs
    inside the Hermes data directory instead of the OS-level ``/root`` or
    ``~/``.  This provides:

    * **Docker persistence** — tool configs land inside the persistent volume.
    * **Profile isolation** — each profile gets its own git identity, SSH
      keys, gh tokens, etc.

    The Python process's own ``os.environ["HOME"]`` and ``Path.home()`` are
    **never** modified — only subprocess environments should inject this value.
    Activation is directory-based: if the ``home/`` subdirectory doesn't
    exist, returns ``None`` and behavior is unchanged.
    """
    hermes_home = get_hermes_home_override()
    if not hermes_home:
        hermes_home = str(get_hermes_home())
    if not hermes_home:
        return None
    profile_home = os.path.join(hermes_home, "home")
    if os.path.isdir(profile_home):
        return profile_home
    return None


VALID_REASONING_EFFORTS = ("minimal", "low", "medium", "high", "xhigh")


def parse_reasoning_effort(effort: str) -> dict | None:
    """Parse a reasoning effort level into a config dict.

    Valid levels: "none", "minimal", "low", "medium", "high", "xhigh".
    Returns None when the input is empty or unrecognized (caller uses default).
    Returns {"enabled": False} for "none".
    Returns {"enabled": True, "effort": <level>} for valid effort levels.
    """
    if not effort or not effort.strip():
        return None
    effort = effort.strip().lower()
    if effort == "none":
        return {"enabled": False}
    if effort in VALID_REASONING_EFFORTS:
        return {"enabled": True, "effort": effort}
    return None


def is_termux() -> bool:
    """Return True when running inside a Termux (Android) environment.

    Checks ``TERMUX_VERSION`` (set by Termux) or the Termux-specific
    ``PREFIX`` path.  Import-safe — no heavy deps.
    """
    prefix = os.getenv("PREFIX", "")
    return bool(os.getenv("TERMUX_VERSION") or "com.termux/files/usr" in prefix)


_wsl_detected: bool | None = None


def is_wsl() -> bool:
    """Return True when running inside WSL (Windows Subsystem for Linux).

    Checks ``/proc/version`` for the ``microsoft`` marker that both WSL1
    and WSL2 inject.  Result is cached for the process lifetime.
    Import-safe — no heavy deps.
    """
    global _wsl_detected
    if _wsl_detected is not None:
        return _wsl_detected
    try:
        with open("/proc/version", "r", encoding="utf-8") as f:
            _wsl_detected = "microsoft" in f.read().lower()
    except Exception:
        _wsl_detected = False
    return _wsl_detected


_container_detected: bool | None = None


def is_container() -> bool:
    """Return True when running inside a Docker/Podman container.

    Checks ``/.dockerenv`` (Docker), ``/run/.containerenv`` (Podman),
    and ``/proc/1/cgroup`` for container runtime markers.  Result is
    cached for the process lifetime.  Import-safe — no heavy deps.
    """
    global _container_detected
    if _container_detected is not None:
        return _container_detected
    if os.path.exists("/.dockerenv"):
        _container_detected = True
        return True
    if os.path.exists("/run/.containerenv"):
        _container_detected = True
        return True
    try:
        with open("/proc/1/cgroup", "r", encoding="utf-8") as f:
            cgroup = f.read()
            if "docker" in cgroup or "podman" in cgroup or "/lxc/" in cgroup:
                _container_detected = True
                return True
    except OSError:
        pass
    _container_detected = False
    return False


# ─── Well-Known Paths ─────────────────────────────────────────────────────────


def get_config_path() -> Path:
    """Return the path to ``config.yaml``.

    - 无 profile / default：``{HUB_DATA_DIR}/config.yaml``（全局）
    - 命名 profile（``HERMES_PROFILE`` 或 override）：``profiles/<name>/config.yaml``
    """
    override = get_hermes_home_override()
    if override:
        return Path(override) / "config.yaml"
    home = get_hermes_home()
    base = _agent_base_dir()
    if home != base:
        return home / "config.yaml"
    return base / "config.yaml"


def get_skills_dir() -> Path:
    """Return the path to the skills directory under HERMES_HOME."""
    return get_hermes_home() / "skills"



def get_env_path() -> Path:
    """Return the path to the ``.env`` file（``HUB_DATA_DIR`` 根）。"""
    return _agent_base_dir() / ".env"


# ─── Network Preferences ─────────────────────────────────────────────────────


def apply_ipv4_preference(force: bool = False) -> None:
    """Monkey-patch ``socket.getaddrinfo`` to prefer IPv4 connections.

    On servers with broken or unreachable IPv6, Python tries AAAA records
    first and hangs for the full TCP timeout before falling back to IPv4.
    This affects httpx, requests, urllib, the OpenAI SDK — everything that
    uses ``socket.getaddrinfo``.

    When *force* is True, patches ``getaddrinfo`` so that calls with
    ``family=AF_UNSPEC`` (the default) resolve as ``AF_INET`` instead,
    skipping IPv6 entirely.  If no A record exists, falls back to the
    original unfiltered resolution so pure-IPv6 hosts still work.

    Safe to call multiple times — only patches once.
    Set ``network.force_ipv4: true`` in ``config.yaml`` to enable.
    """
    if not force:
        return

    import socket

    # Guard against double-patching
    if getattr(socket.getaddrinfo, "_hermes_ipv4_patched", False):
        return

    _original_getaddrinfo = socket.getaddrinfo

    def _ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if family == 0:  # AF_UNSPEC — caller didn't request a specific family
            try:
                return _original_getaddrinfo(
                    host, port, socket.AF_INET, type, proto, flags
                )
            except socket.gaierror:
                # No A record — fall back to full resolution (pure-IPv6 hosts)
                return _original_getaddrinfo(host, port, family, type, proto, flags)
        return _original_getaddrinfo(host, port, family, type, proto, flags)

    _ipv4_getaddrinfo._hermes_ipv4_patched = True  # type: ignore[attr-defined]
    socket.getaddrinfo = _ipv4_getaddrinfo  # type: ignore[assignment]


# ─── Streaming Response Constants ────────────────────────────────────────────

# Response ID for partial stream stubs used during error recovery
PARTIAL_STREAM_STUB_ID = "partial-stream-stub"

FINISH_REASON_LENGTH = "length"


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODELS_URL = f"{OPENROUTER_BASE_URL}/models"

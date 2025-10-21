from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional

import httpx
import yaml

from ..models.remote_access_config import (
    CloudflareConfig,
    NgrokConfig,
    RemoteAccessConfig,
    RemoteAccessProvider,
)

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(os.getenv("REMOTE_ACCESS_CONFIG_PATH", "/home/pi/lawnberry/config/remote_access.json"))
STATUS_PATH = Path(os.getenv("REMOTE_ACCESS_STATUS_PATH", "/home/pi/lawnberry/data/remote_access_status.json"))
NGROK_CONFIG_DIR = Path(os.getenv("NGROK_CONFIG_DIR", str(Path.home() / ".config" / "ngrok")))
NGROK_CONFIG_FILE = NGROK_CONFIG_DIR / "lawnberry.yml"
DEFAULT_NGROK_API_PORT = int(os.getenv("NGROK_API_PORT", "4040"))
DEFAULT_CLOUDFLARE_METRICS_PORT = int(os.getenv("CLOUDFLARE_METRICS_PORT", "53123"))
HEALTH_FAILURE_THRESHOLD = 3
HEALTH_TIMEOUT_SECONDS = 6.0


def _atomic_json_dump(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    os.replace(tmp_path, path)


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:  # pragma: no cover - defensive
        logger.debug("Failed to read JSON from %s", path, exc_info=True)
        return {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class RemoteAccessStatus:
    provider: str
    configured_provider: str
    enabled: bool
    active: bool
    url: Optional[str] = None
    message: Optional[str] = None
    last_error: Optional[str] = None
    last_checked: Optional[datetime] = None
    fallback_provider: Optional[str] = None
    health: str = "unknown"
    version: int = 1

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["last_checked"] = self.last_checked.isoformat() if self.last_checked else None
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RemoteAccessStatus:
        value = data.get("last_checked")
        last_checked: Optional[datetime] = None
        if isinstance(value, str):
            try:
                last_checked = datetime.fromisoformat(value)
            except Exception:  # pragma: no cover - defensive
                last_checked = None
        provider = data.get("provider", RemoteAccessProvider.DISABLED.value)
        configured = data.get("configured_provider", provider)
        return cls(
            provider=provider,
            configured_provider=configured,
            enabled=bool(data.get("enabled", False)),
            active=bool(data.get("active", False)),
            url=data.get("url"),
            message=data.get("message"),
            last_error=data.get("last_error"),
            last_checked=last_checked,
            fallback_provider=data.get("fallback_provider"),
            health=data.get("health", "unknown"),
            version=int(data.get("version", 1)),
        )


class RemoteAccessError(RuntimeError):
    """Raised when tunnel configuration or startup fails."""


ProcessFactory = Callable[..., Awaitable[asyncio.subprocess.Process]]


class RemoteAccessService:
    """Manage remote access tunnels (Cloudflare, ngrok, or custom)."""

    def __init__(
        self,
        config_path: Path = CONFIG_PATH,
        status_path: Path = STATUS_PATH,
        process_factory: Optional[ProcessFactory] = None,
        metrics_port: int = DEFAULT_CLOUDFLARE_METRICS_PORT,
        ngrok_api_port: int = DEFAULT_NGROK_API_PORT,
    ) -> None:
        self._config_path = Path(config_path)
        self._status_path = Path(status_path)
        self._process_factory = process_factory or self._spawn_process
        self._metrics_port = int(metrics_port)
        self._ngrok_api_port = int(ngrok_api_port)

        self._config: RemoteAccessConfig = self.load_config_from_disk(self._config_path)
        self._status: RemoteAccessStatus = self.load_status_from_disk(
            self._status_path,
            configured_provider=self._config.provider,
            enabled=self._config.enabled,
        )
        self._process: Optional[asyncio.subprocess.Process] = None
        self._stdout_task: Optional[asyncio.Task[Any]] = None
        self._stderr_task: Optional[asyncio.Task[Any]] = None
        self._monitor_task: Optional[asyncio.Task[Any]] = None
        self._health_failures: int = 0
        self._fallback_active: Optional[str] = None
        self._config_digest: str = self._digest_config(self._config)

        # Persist initial status for consumers on boot
        self._persist_status()

    @property
    def config_path(self) -> Path:
        return self._config_path

    @property
    def status_path(self) -> Path:
        return self._status_path

    @property
    def config_digest(self) -> str:
        return self._config_digest

    def get_config(self) -> RemoteAccessConfig:
        return self._config

    def get_status(self) -> RemoteAccessStatus:
        return self._status

    @staticmethod
    def load_config_from_disk(path: Path = CONFIG_PATH) -> RemoteAccessConfig:
        raw = _load_json(path)
        try:
            return RemoteAccessConfig(**raw)
        except Exception:
            logger.warning("Invalid remote access config on disk, regenerating defaults")
            return RemoteAccessConfig()

    @staticmethod
    def save_config_to_disk(cfg: RemoteAccessConfig, path: Path = CONFIG_PATH) -> None:
        payload = cfg.model_dump(mode="json")
        _atomic_json_dump(path, payload)

    @staticmethod
    def load_status_from_disk(
        path: Path = STATUS_PATH,
        *,
        configured_provider: str | None = None,
        enabled: bool | None = None,
    ) -> RemoteAccessStatus:
        raw = _load_json(path)
        if not raw:
            provider = configured_provider or RemoteAccessProvider.DISABLED.value
            return RemoteAccessStatus(
                provider=provider,
                configured_provider=provider,
                enabled=bool(enabled),
                active=False,
                message="idle",
            )
        status = RemoteAccessStatus.from_dict(raw)
        if configured_provider is not None:
            status.configured_provider = configured_provider
        if enabled is not None:
            status.enabled = bool(enabled)
        return status

    @staticmethod
    def save_status_to_disk(status: RemoteAccessStatus, path: Path = STATUS_PATH) -> None:
        _atomic_json_dump(path, status.to_dict())

    def configure(self, cfg: RemoteAccessConfig, *, persist: bool = True) -> None:
        self._validate_config(cfg)
        self._config = cfg
        self._config_digest = self._digest_config(cfg)
        self._status.configured_provider = cfg.provider
        self._status.enabled = cfg.enabled
        if persist:
            self.save_config_to_disk(cfg, self._config_path)
        self._persist_status()

    async def apply_configuration(self, cfg: RemoteAccessConfig, *, persist: bool = False) -> None:
        self.configure(cfg, persist=persist)
        if not cfg.enabled or cfg.provider == RemoteAccessProvider.DISABLED.value:
            await self.disable()
        else:
            await self.enable()

    async def enable(self) -> None:
        provider = self._coerce_provider(self._config.provider)
        if provider == RemoteAccessProvider.DISABLED or not self._config.enabled:
            await self.disable()
            return

        self._status.enabled = True
        self._status.configured_provider = provider.value
        self._status.fallback_provider = None
        self._status.last_error = None
        self._fallback_active = None

        try:
            if provider is RemoteAccessProvider.CLOUDFLARE:
                await self._start_cloudflare(self._config.cloudflare)
            elif provider is RemoteAccessProvider.NGROK:
                await self._start_ngrok(self._config.ngrok, fallback=False)
            elif provider is RemoteAccessProvider.CUSTOM:
                await self._start_custom(self._config.custom.command, self._config.custom.env)
            else:
                raise RemoteAccessError(f"Unsupported provider: {provider.value}")
        except RemoteAccessError as exc:
            logger.error("Failed to start %s tunnel: %s", provider.value, exc)
            self._status.active = False
            self._status.message = f"{provider.value} startup failed"
            self._status.last_error = str(exc)
            if self._has_ngrok_fallback(provider):
                logger.warning("Falling back to ngrok tunnel due to %s failure", provider.value)
                await self._start_ngrok(self._config.ngrok, fallback=True)
                self._persist_status()
            else:
                self._persist_status()
                raise
        else:
            self._persist_status()

    async def disable(self) -> None:
        self._status.enabled = False
        await self._stop_process()
        self._status.active = False
        self._status.health = "stopped"
        self._status.message = "remote access disabled"
        self._status.url = None
        self._status.fallback_provider = None
        self._persist_status()

    async def check_health(self) -> None:
        provider_value = self._status.provider
        provider = self._coerce_provider(provider_value)
        if not self._config.enabled or provider == RemoteAccessProvider.DISABLED:
            self._status.active = False
            self._status.health = "disabled"
            self._persist_status()
            return

        process = self._process
        if process is None or process.returncode is not None:
            logger.warning("Tunnel process for %s is not running; attempting restart", provider_value)
            self._status.active = False
            self._status.health = "restarting"
            await self.enable()
            return

        healthy = True
        new_url: Optional[str] = self._status.url
        try:
            if provider is RemoteAccessProvider.CLOUDFLARE:
                healthy = await self._check_cloudflare_health()
                if self._config.cloudflare.hostname:
                    new_url = self._config.cloudflare.hostname
            elif provider is RemoteAccessProvider.NGROK:
                healthy, discovered = await self._check_ngrok_health()
                if discovered:
                    new_url = discovered
        except Exception as exc:  # pragma: no cover - defensive
            healthy = False
            logger.debug("Health probe raised: %s", exc, exc_info=True)

        self._status.url = new_url
        if healthy:
            self._status.active = True
            self._status.health = "healthy"
            self._status.message = f"{provider_value} tunnel healthy"
            self._status.last_error = None
            self._health_failures = 0
        else:
            self._health_failures += 1
            self._status.health = "degraded"
            self._status.active = self._health_failures < HEALTH_FAILURE_THRESHOLD
            self._status.message = f"{provider_value} health probe failed ({self._health_failures})"
            if self._health_failures >= HEALTH_FAILURE_THRESHOLD:
                logger.warning("Health failure threshold reached; restarting %s tunnel", provider_value)
                self._health_failures = 0
                await self.enable()
                return
        self._persist_status()

    def record_error(self, message: str, exc: Optional[Exception] = None) -> None:
        logger.error(message, exc_info=exc)
        self._status.active = False
        self._status.health = "error"
        self._status.message = message
        self._status.last_error = str(exc) if exc else message
        self._persist_status()

    def _persist_status(self) -> None:
        self._status.last_checked = _now()
        self.save_status_to_disk(self._status, self._status_path)

    def _validate_config(self, cfg: RemoteAccessConfig) -> None:
        provider = self._coerce_provider(cfg.provider)
        if provider is RemoteAccessProvider.CLOUDFLARE and cfg.enabled:
            if not cfg.cloudflare or not cfg.cloudflare.tunnel_name:
                raise RemoteAccessError("Cloudflare tunnel_name is required when enabled")
            if cfg.cloudflare.credentials_file and not Path(cfg.cloudflare.credentials_file).exists():
                raise RemoteAccessError("Cloudflare credentials file not found")
        if provider is RemoteAccessProvider.NGROK and cfg.enabled:
            if not cfg.ngrok or not cfg.ngrok.authtoken:
                raise RemoteAccessError("ngrok authtoken is required when enabled")
        if provider is RemoteAccessProvider.CUSTOM and cfg.enabled:
            command = cfg.custom.command if cfg.custom else None
            if not command:
                raise RemoteAccessError("Custom tunnel command must be provided")

    async def _start_cloudflare(self, cfg: CloudflareConfig) -> None:
        binary = self._ensure_binary("cloudflared")
        cmd = [binary, "tunnel", "--no-autoupdate", "--metrics", f"127.0.0.1:{self._metrics_port}", "run"]
        if cfg.credentials_file:
            cmd.extend(["--cred-file", cfg.credentials_file])
        if cfg.tunnel_name:
            cmd.append(cfg.tunnel_name)
        env = os.environ.copy()
        await self._launch_process(RemoteAccessProvider.CLOUDFLARE, cmd, env)
        self._status.provider = RemoteAccessProvider.CLOUDFLARE.value
        self._status.active = True
        self._status.message = "Cloudflare tunnel running"
        self._status.url = cfg.hostname or self._status.url
        self._status.fallback_provider = None
        self._status.health = "starting"

    async def _start_ngrok(self, cfg: NgrokConfig, *, fallback: bool) -> None:
        binary = self._ensure_binary("ngrok")
        config_path = self._ensure_ngrok_config(cfg)
        cmd = [
            binary,
            "start",
            "--config",
            str(config_path),
            "--log",
            "stdout",
            "--log-format",
            "json",
            "lawnberry-api",
            "lawnberry-web",
        ]
        env = os.environ.copy()
        await self._launch_process(RemoteAccessProvider.NGROK, cmd, env)
        self._status.provider = RemoteAccessProvider.NGROK.value
        self._status.active = True
        self._status.message = "ngrok tunnel running"
        self._status.fallback_provider = RemoteAccessProvider.NGROK.value if fallback else None
        self._status.health = "starting"
        # URL will be refreshed via health check once ngrok publishes tunnels

    async def _start_custom(self, command: Optional[str], env_map: Dict[str, str]) -> None:
        if not command:
            raise RemoteAccessError("Custom tunnel command missing")
        env = os.environ.copy()
        env.update(env_map or {})
        cmd = ["/bin/bash", "-lc", command]
        await self._launch_process(RemoteAccessProvider.CUSTOM, cmd, env)
        self._status.provider = RemoteAccessProvider.CUSTOM.value
        self._status.active = True
        self._status.message = "Custom tunnel running"
        self._status.fallback_provider = None
        self._status.health = "starting"

    def _ensure_binary(self, binary: str) -> str:
        path = shutil.which(binary)
        if not path:
            raise RemoteAccessError(f"{binary} binary not found on PATH")
        return path

    def _ensure_ngrok_config(self, cfg: NgrokConfig) -> Path:
        if not cfg.authtoken:
            raise RemoteAccessError("ngrok authtoken missing")
        NGROK_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        config_data: Dict[str, Any] = {
            "version": "2",
            "authtoken": cfg.authtoken,
            "web_addr": f"127.0.0.1:{self._ngrok_api_port}",
            "tunnels": {
                "lawnberry-api": {"proto": "http", "addr": "127.0.0.1:8081", "inspect": False},
                "lawnberry-web": {"proto": "http", "addr": "127.0.0.1:3000", "inspect": False},
            },
        }
        if cfg.region:
            config_data["region"] = cfg.region
        if cfg.edge:
            labels = [f"edge={cfg.edge}"]
            config_data["tunnels"]["lawnberry-api"]["labels"] = labels
            config_data["tunnels"]["lawnberry-web"]["labels"] = labels

        existing = {}
        if NGROK_CONFIG_FILE.exists():
            try:
                existing = yaml.safe_load(NGROK_CONFIG_FILE.read_text()) or {}
            except Exception:  # pragma: no cover - defensive
                existing = {}
        if existing != config_data:
            NGROK_CONFIG_FILE.write_text(yaml.safe_dump(config_data, sort_keys=True))
            try:
                os.chmod(NGROK_CONFIG_FILE, 0o600)
            except Exception:  # pragma: no cover
                logger.debug("Unable to chmod ngrok config file", exc_info=True)
        return NGROK_CONFIG_FILE

    async def _launch_process(
        self,
        provider: RemoteAccessProvider,
        command: list[str],
        env: Optional[Dict[str, str]],
    ) -> None:
        await self._stop_process()
        logger.info("Starting %s tunnel: %s", provider.value, " ".join(command))
        process = await self._process_factory(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._process = process
        if process.stdout:
            self._stdout_task = asyncio.create_task(self._stream_output(process.stdout, logging.INFO, provider.value))
        if process.stderr:
            self._stderr_task = asyncio.create_task(self._stream_output(process.stderr, logging.WARNING, provider.value))
        self._monitor_task = asyncio.create_task(self._monitor_process(provider))
        self._status.provider = provider.value

    async def _stop_process(self) -> None:
        proc = self._process
        if not proc:
            return
        logger.info("Stopping tunnel process (pid=%s)", getattr(proc, "pid", "unknown"))
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=10)
        except asyncio.TimeoutError:
            logger.warning("Tunnel process did not exit in time; killing")
            proc.kill()
            await proc.wait()
        except ProcessLookupError:  # pragma: no cover - defensive
            pass
        finally:
            self._process = None

        for task in (self._stdout_task, self._stderr_task, self._monitor_task):
            if task:
                task.cancel()
        self._stdout_task = self._stderr_task = self._monitor_task = None

    async def _stream_output(self, stream: asyncio.StreamReader, level: int, prefix: str) -> None:
        try:
            while True:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode(errors="ignore").strip()
                if text:
                    logger.log(level, "[%s] %s", prefix, text)
        except asyncio.CancelledError:  # pragma: no cover - expected when stopping
            return

    async def _monitor_process(self, provider: RemoteAccessProvider) -> None:
        proc = self._process
        if not proc:
            return
        try:
            returncode = await proc.wait()
        except asyncio.CancelledError:  # pragma: no cover - stopping
            return
        logger.warning("%s tunnel process exited with code %s", provider.value, returncode)
        self._process = None
        self._status.active = False
        self._status.health = "stopped"
        self._status.message = f"{provider.value} tunnel exited"
        self._status.last_error = f"exit_code={returncode}"
        self._persist_status()

    async def _check_cloudflare_health(self) -> bool:
        url = f"http://127.0.0.1:{self._metrics_port}/metrics"
        async with httpx.AsyncClient(timeout=httpx.Timeout(HEALTH_TIMEOUT_SECONDS)) as client:
            response = await client.get(url)
        return response.status_code == 200 and b"cloudflare_tunnel_connected" in response.content

    async def _check_ngrok_health(self) -> tuple[bool, Optional[str]]:
        url = f"http://127.0.0.1:{self._ngrok_api_port}/api/tunnels"
        async with httpx.AsyncClient(timeout=httpx.Timeout(HEALTH_TIMEOUT_SECONDS)) as client:
            response = await client.get(url)
        if response.status_code != 200:
            return False, None
        try:
            data = response.json()
        except Exception:  # pragma: no cover - defensive
            return False, None
        tunnels = data.get("tunnels") or []
        public_url = None
        for tunnel in tunnels:
            public_url = tunnel.get("public_url") or public_url
        return bool(tunnels), public_url

    def _has_ngrok_fallback(self, primary: RemoteAccessProvider) -> bool:
        return (
            primary is not RemoteAccessProvider.NGROK
            and self._config.ngrok is not None
            and bool(self._config.ngrok.authtoken)
        )

    def _coerce_provider(self, value: str) -> RemoteAccessProvider:
        try:
            return RemoteAccessProvider(value)
        except ValueError:
            return RemoteAccessProvider.DISABLED

    def _digest_config(self, cfg: RemoteAccessConfig) -> str:
        return json.dumps(cfg.model_dump(mode="json"), sort_keys=True)

    async def _spawn_process(
        self,
        *args: str,
        stdout: Any = asyncio.subprocess.PIPE,
        stderr: Any = asyncio.subprocess.PIPE,
        env: Optional[Dict[str, str]] = None,
    ) -> asyncio.subprocess.Process:
        return await asyncio.create_subprocess_exec(*args, stdout=stdout, stderr=stderr, env=env)


remote_access_service = RemoteAccessService()

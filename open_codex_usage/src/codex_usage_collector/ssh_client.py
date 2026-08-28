from __future__ import annotations

import getpass
import shlex
from pathlib import Path
from typing import Any

import paramiko

from codex_usage_collector.config import HostConfig


class RemoteSSHClient:
    def __init__(self, host_config: HostConfig) -> None:
        self._host_config = host_config
        self._client: paramiko.SSHClient | None = None

    def connect(self) -> None:
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(**self._build_connect_kwargs())
        self._client = client

    def list_json_files(self, remote_path: str) -> list[str]:
        command = "sh -lc " + shlex.quote(
            f"find {remote_path} -type f \\( -name '*.json' -o -name '*.jsonl' \\) 2>/dev/null | sort || true"
        )
        stdout = self._run_command(command)
        return [line.strip() for line in stdout.splitlines() if line.strip()]

    def read_file(self, remote_path: str) -> str:
        client = self._require_client()
        with client.open_sftp() as sftp:
            with sftp.open(remote_path, "r") as handle:
                content = handle.read()
        if isinstance(content, bytes):
            return content.decode("utf-8")
        return str(content)

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> RemoteSSHClient:
        self.connect()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def _run_command(self, command: str) -> str:
        client = self._require_client()
        _, stdout, stderr = client.exec_command(command)
        stderr_text = stderr.read().decode("utf-8").strip()
        stdout_text = stdout.read().decode("utf-8")
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0 and stderr_text:
            raise RuntimeError(stderr_text)
        return stdout_text

    def _require_client(self) -> paramiko.SSHClient:
        if self._client is None:
            raise RuntimeError("SSH client is not connected")
        return self._client

    def _build_connect_kwargs(self) -> dict[str, Any]:
        ssh_options = self._lookup_ssh_config(self._host_config.hostname)
        username = self._host_config.user or ssh_options.get("user") or getpass.getuser()
        hostname = ssh_options.get("hostname") or self._host_config.hostname
        port = self._resolve_port(ssh_options.get("port"), self._host_config.port)
        key_filenames = self._resolve_key_filenames(ssh_options)

        connect_kwargs: dict[str, Any] = {
            "hostname": hostname,
            "port": port,
            "username": username,
            "allow_agent": True,
            "look_for_keys": key_filenames is None,
        }
        if key_filenames is not None:
            connect_kwargs["key_filename"] = key_filenames

        proxy_command = ssh_options.get("proxycommand")
        if isinstance(proxy_command, str) and proxy_command.strip():
            connect_kwargs["sock"] = paramiko.ProxyCommand(proxy_command)

        return connect_kwargs

    def _resolve_key_filenames(self, ssh_options: dict[str, Any]) -> list[str] | str | None:
        if self._host_config.key_path is not None:
            return str(self._host_config.key_path)

        identity_files = ssh_options.get("identityfile")
        if isinstance(identity_files, list):
            expanded = [str(Path(path).expanduser()) for path in identity_files if isinstance(path, str)]
            return expanded or None
        if isinstance(identity_files, str) and identity_files.strip():
            return str(Path(identity_files).expanduser())
        return None

    def _resolve_port(self, ssh_port: Any, configured_port: int | None) -> int:
        if configured_port is not None:
            return configured_port
        if isinstance(ssh_port, str) and ssh_port.isdigit():
            return int(ssh_port)
        return 22

    def _lookup_ssh_config(self, host_alias: str) -> dict[str, Any]:
        config_path = Path("~/.ssh/config").expanduser()
        if not config_path.exists():
            return {}

        ssh_config = paramiko.SSHConfig()
        with config_path.open("r", encoding="utf-8") as handle:
            ssh_config.parse(handle)
        return ssh_config.lookup(host_alias)

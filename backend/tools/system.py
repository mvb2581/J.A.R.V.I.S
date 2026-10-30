"""Informações do sistema, processos, volume e controle de mídia."""

from __future__ import annotations

import ctypes
import logging
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime
from typing import Any

import psutil

from backend.tools.base import BaseTool, ToolContext, ToolResult

logger = logging.getLogger(__name__)

_GPU_CACHE: tuple[float, list[dict[str, Any]]] = (0.0, [])
_GPU_CACHE_SECONDS = 5.0


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).astimezone().isoformat(timespec="seconds")


def _nvidia_gpus() -> list[dict[str, Any]]:
    global _GPU_CACHE
    now = time.monotonic()
    if now - _GPU_CACHE[0] < _GPU_CACHE_SECONDS:
        return _GPU_CACHE[1]
    gpus: list[dict[str, Any]] = []
    executable = shutil.which("nvidia-smi")
    if executable:
        try:
            completed = subprocess.run(
                [
                    executable,
                    "--query-gpu=name,utilization.gpu,memory.total,memory.used,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=4,
                check=False,
            )
            if completed.returncode == 0:
                for line in completed.stdout.strip().splitlines():
                    parts = [part.strip() for part in line.split(",")]
                    if len(parts) >= 5:
                        gpus.append(
                            {
                                "name": parts[0],
                                "utilization_percent": float(parts[1]),
                                "memory_total_mb": float(parts[2]),
                                "memory_used_mb": float(parts[3]),
                                "temperature_c": float(parts[4]),
                                "vendor": "NVIDIA",
                            }
                        )
        except (OSError, ValueError, subprocess.SubprocessError):
            logger.debug("nvidia-smi indisponível ou falhou", exc_info=True)
    _GPU_CACHE = (now, gpus)
    return gpus


def _gpu_names_wmi() -> list[str]:
    if sys.platform != "win32":
        return []
    try:
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "(Get-CimInstance Win32_VideoController).Name",
            ],
            capture_output=True,
            text=True,
            timeout=6,
            check=False,
        )
        return [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.SubprocessError):
        return []


def collect_gpu_info() -> list[dict[str, Any]]:
    gpus = _nvidia_gpus()
    if gpus:
        return gpus
    return [{"name": name, "vendor": "unknown", "utilization_percent": None} for name in _gpu_names_wmi()]


def collect_resource_usage() -> dict[str, Any]:
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk_path = os.environ.get("SystemDrive", "C:") + "\\"
    try:
        disk = psutil.disk_usage(disk_path)
    except OSError:
        disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()
    battery: dict[str, Any] | None = None
    try:
        sensor = psutil.sensors_battery()
        if sensor:
            battery = {
                "percent": round(sensor.percent, 1),
                "plugged": sensor.power_plugged,
                "seconds_left": sensor.secsleft if sensor.secsleft >= 0 else None,
            }
    except (AttributeError, NotImplementedError):
        battery = None
    gpus = collect_gpu_info()
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.15),
        "cpu_cores_logical": psutil.cpu_count(logical=True),
        "cpu_cores_physical": psutil.cpu_count(logical=False),
        "ram_percent": memory.percent,
        "ram_used_gb": round(memory.used / (1024**3), 2),
        "ram_total_gb": round(memory.total / (1024**3), 2),
        "swap_percent": swap.percent,
        "disk_percent": disk.percent,
        "disk_used_gb": round(disk.used / (1024**3), 2),
        "disk_total_gb": round(disk.total / (1024**3), 2),
        "network_sent_mb": round(net.bytes_sent / (1024**2), 1),
        "network_received_mb": round(net.bytes_recv / (1024**2), 1),
        "gpus": gpus,
        "battery": battery,
        "processes": len(psutil.pids()),
        "uptime_seconds": int(time.time() - psutil.boot_time()),
    }


class GetSystemInformationTool(BaseTool):
    name = "get_system_information"
    description = (
        "Retorna informações reais do Windows: versão, usuário, CPU, memória, discos, GPU, "
        "bateria, rede e tempo ligado. Use antes de responder perguntas sobre o computador."
    )
    permission_level = 1
    category = "system"
    parameters = {
        "type": "object",
        "properties": {"include_gpu": {"type": "boolean", "default": True}},
        "additionalProperties": False,
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        memory = psutil.virtual_memory()
        disks: list[dict[str, Any]] = []
        for partition in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(partition.mountpoint)
            except OSError:
                continue
            disks.append(
                {
                    "device": partition.device,
                    "mountpoint": partition.mountpoint,
                    "filesystem": partition.fstype,
                    "total_gb": round(usage.total / (1024**3), 2),
                    "used_gb": round(usage.used / (1024**3), 2),
                    "percent": usage.percent,
                }
            )
        info: dict[str, Any] = {
            "os": {
                "system": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
                "architecture": platform.machine(),
                "hostname": socket.gethostname(),
                "user": os.environ.get("USERNAME") or os.environ.get("USER"),
            },
            "cpu": {
                "name": platform.processor() or platform.uname().processor,
                "physical_cores": psutil.cpu_count(logical=False),
                "logical_cores": psutil.cpu_count(logical=True),
                "frequency_mhz": round(psutil.cpu_freq().current, 0) if psutil.cpu_freq() else None,
            },
            "memory": {
                "total_gb": round(memory.total / (1024**3), 2),
                "available_gb": round(memory.available / (1024**3), 2),
                "used_gb": round(memory.used / (1024**3), 2),
                "percent": memory.percent,
            },
            "disks": disks,
            "boot_time": _iso(psutil.boot_time()),
            "uptime_seconds": int(time.time() - psutil.boot_time()),
            "python": sys.version.split()[0],
            "local_ip": _local_ip(),
        }
        if arguments.get("include_gpu", True):
            info["gpus"] = collect_gpu_info()
        try:
            battery = psutil.sensors_battery()
            if battery:
                info["battery"] = {
                    "percent": round(battery.percent, 1),
                    "plugged": battery.power_plugged,
                }
        except (AttributeError, NotImplementedError):
            pass
        return ToolResult.ok(
            info,
            display=(
                f"{info['os']['system']} {info['os']['release']} | "
                f"RAM {info['memory']['used_gb']}/{info['memory']['total_gb']} GB"
            ),
        )


def _local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


class GetResourceUsageTool(BaseTool):
    name = "get_resource_usage"
    description = "Retorna uso atual de CPU, RAM, disco, rede, GPU e bateria."
    permission_level = 1
    category = "system"
    parameters = {"type": "object", "properties": {}, "additionalProperties": False}

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        usage = collect_resource_usage()
        gpu_text = ""
        if usage["gpus"]:
            gpu = usage["gpus"][0]
            gpu_text = f" | GPU {gpu.get('name', '?')}"
            if gpu.get("utilization_percent") is not None:
                gpu_text += f" {gpu['utilization_percent']:.0f}%"
        return ToolResult.ok(
            usage,
            display=(
                f"CPU {usage['cpu_percent']:.0f}% | RAM {usage['ram_percent']:.0f}% "
                f"({usage['ram_used_gb']}/{usage['ram_total_gb']} GB){gpu_text}"
            ),
        )


class GetProcessListTool(BaseTool):
    name = "get_process_list"
    description = "Lista processos em execução, com CPU, memória e usuário. Pode filtrar por nome."
    permission_level = 1
    category = "system"
    parameters = {
        "type": "object",
        "properties": {
            "filter": {"type": "string", "maxLength": 100, "description": "Trecho do nome do processo."},
            "sort_by": {"type": "string", "enum": ["cpu", "memory", "name"], "default": "memory"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 30},
        },
        "additionalProperties": False,
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        filter_text = (arguments.get("filter") or "").lower().strip()
        sort_by = arguments.get("sort_by", "memory")
        limit = int(arguments.get("limit", 30))
        processes: list[psutil.Process] = []
        for process in psutil.process_iter(["name"]):
            name = (process.info.get("name") or "").lower()
            if filter_text and filter_text not in name:
                continue
            processes.append(process)
        for process in processes:
            try:
                process.cpu_percent(interval=None)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        time.sleep(0.12)
        rows: list[dict[str, Any]] = []
        for process in processes:
            try:
                with process.oneshot():
                    memory_info = process.memory_info()
                    rows.append(
                        {
                            "pid": process.pid,
                            "name": process.name(),
                            "username": _safe_username(process),
                            "status": process.status(),
                            "cpu_percent": round(process.cpu_percent(interval=None), 1),
                            "memory_mb": round(memory_info.rss / (1024**2), 1),
                            "created": _iso(process.create_time()),
                        }
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                continue
        if sort_by == "cpu":
            rows.sort(key=lambda item: item["cpu_percent"], reverse=True)
        elif sort_by == "name":
            rows.sort(key=lambda item: item["name"].lower())
        else:
            rows.sort(key=lambda item: item["memory_mb"], reverse=True)
        rows = rows[:limit]
        return ToolResult.ok(
            {"processes": rows, "total_matched": len(processes)},
            display=f"{len(rows)} processo(s) listado(s)",
        )


def _safe_username(process: psutil.Process) -> str:
    try:
        return process.username()
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        return "?"


class ControlVolumeTool(BaseTool):
    name = "control_volume"
    description = "Consulta ou altera o volume master do Windows (get, set, up, down, mute, unmute, toggle)."
    permission_level = 1
    category = "system"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["get", "set", "up", "down", "mute", "unmute", "toggle"],
                "default": "get",
            },
            "value": {"type": "integer", "minimum": 0, "maximum": 100},
        },
        "additionalProperties": False,
    }

    def _volume(self) -> Any:
        if sys.platform != "win32":
            raise RuntimeError("Controle de volume implementado para Windows")
        from pycaw.pycaw import AudioUtilities

        device = AudioUtilities.GetSpeakers()
        endpoint = getattr(device, "EndpointVolume", None)
        if endpoint is not None:
            return endpoint
        from ctypes import POINTER, cast

        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import IAudioEndpointVolume

        interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(interface, POINTER(IAudioEndpointVolume))

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        action = arguments.get("action", "get")
        try:
            volume = self._volume()
            current = float(volume.GetMasterVolumeLevelScalar())
            muted = bool(volume.GetMute())
            if action == "set":
                if arguments.get("value") is None:
                    return ToolResult.fail("Informe value entre 0 e 100 para action=set")
                current = max(0.0, min(1.0, float(arguments["value"]) / 100.0))
                volume.SetMasterVolumeLevelScalar(current, None)
            elif action in {"up", "down"}:
                step = 0.1 if action == "up" else -0.1
                current = max(0.0, min(1.0, current + step))
                volume.SetMasterVolumeLevelScalar(current, None)
            elif action == "mute":
                volume.SetMute(1, None)
            elif action == "unmute":
                volume.SetMute(0, None)
            elif action == "toggle":
                volume.SetMute(0 if muted else 1, None)
            current = float(volume.GetMasterVolumeLevelScalar())
            muted = bool(volume.GetMute())
        except Exception as exc:
            return ToolResult.fail(f"Não foi possível controlar o volume: {exc}")
        percent = round(current * 100)
        return ToolResult.ok(
            {"volume_percent": percent, "muted": muted},
            display=f"Volume em {percent}%" + (" (mudo)" if muted else ""),
        )


class ControlMediaTool(BaseTool):
    name = "control_media"
    description = "Envia teclas de mídia do Windows: play_pause, next, previous, stop, volume_up, volume_down, mute."
    permission_level = 1
    category = "system"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["play_pause", "next", "previous", "stop", "volume_up", "volume_down", "mute"],
            }
        },
        "required": ["action"],
        "additionalProperties": False,
    }

    _KEYS = {
        "play_pause": 0xB3,
        "next": 0xB0,
        "previous": 0xB1,
        "stop": 0xB2,
        "volume_up": 0xAF,
        "volume_down": 0xAE,
        "mute": 0xAD,
    }

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        if sys.platform != "win32":
            return ToolResult.fail("Controle de mídia implementado para Windows")
        action = arguments["action"]
        vk = self._KEYS[action]
        try:
            user32 = ctypes.windll.user32
            user32.keybd_event(vk, 0, 0, 0)
            user32.keybd_event(vk, 0, 0x0002, 0)
        except Exception as exc:
            return ToolResult.fail(f"Não foi possível enviar a tecla de mídia: {exc}")
        return ToolResult.ok({"action": action}, display=f"Tecla de mídia enviada: {action}")

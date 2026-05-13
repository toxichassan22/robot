from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from textwrap import dedent
from zipfile import ZIP_DEFLATED, ZipFile


REPO_ROOT = Path(__file__).resolve().parents[3]
WEB_UI_ROOT = REPO_ROOT / "pi5" / "web_ui"
BACKEND_REQUIREMENTS = WEB_UI_ROOT / "backend" / "requirements.txt"
PORTABLE_ROOT = REPO_ROOT / "output" / "portable-windows" / "RobotControlHost"
ZIP_PATH = REPO_ROOT / "output" / "portable-windows" / "RobotControlHost.zip"
RUNTIME_ROOT = PORTABLE_ROOT / "runtime"
PYTHON_BASE = Path(sys.base_prefix).resolve()


def run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    if os.name == "nt" and command and command[0] in {"npm", "npx"}:
        command = [f"{command[0]}.cmd", *command[1:]]
    subprocess.run(command, cwd=str(cwd) if cwd else None, env=env, check=True)


def clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def copy_tree(src: Path, dst: Path, *, ignore=None) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=ignore)


def copy_python_runtime() -> None:
    runtime_lib = RUNTIME_ROOT / "Lib"
    runtime_lib.mkdir(parents=True, exist_ok=True)

    for name in ["python.exe", "pythonw.exe", "python3.dll", "python314.dll", "vcruntime140.dll", "vcruntime140_1.dll"]:
        src = PYTHON_BASE / name
        if src.exists():
            shutil.copy2(src, RUNTIME_ROOT / name)

    dll_src = PYTHON_BASE / "DLLs"
    if dll_src.exists():
        copy_tree(dll_src, RUNTIME_ROOT / "DLLs")

    def ignore_lib(_directory: str, names: list[str]) -> set[str]:
        ignored = {"site-packages", "__pycache__", "test", "tests", "idlelib", "tkinter", "turtledemo", "venv"}
        return {name for name in names if name in ignored}

    copy_tree(PYTHON_BASE / "Lib", runtime_lib, ignore=ignore_lib)
    (runtime_lib / "site-packages").mkdir(parents=True, exist_ok=True)


def install_python_packages() -> None:
    target = RUNTIME_ROOT / "Lib" / "site-packages"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "sd")
    run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--upgrade",
            "--target",
            str(target),
            "-r",
            str(BACKEND_REQUIREMENTS),
        ],
        cwd=REPO_ROOT,
        env=env,
    )


def copy_application_files() -> None:
    copy_tree(WEB_UI_ROOT / "dist", PORTABLE_ROOT / "dist")
    copy_tree(REPO_ROOT / "data", PORTABLE_ROOT / "data")
    piper_models = REPO_ROOT / "models" / "piper"
    if piper_models.exists():
        copy_tree(piper_models, PORTABLE_ROOT / "models" / "piper")

    sd_root = PORTABLE_ROOT / "sd"
    sd_root.mkdir(parents=True, exist_ok=True)
    copy_tree(REPO_ROOT / "sd" / "pi_5", sd_root / "pi_5")
    copy_tree(REPO_ROOT / "sd" / "brain", sd_root / "brain")
    shared_src = REPO_ROOT / "sd" / "shared"
    if shared_src.exists():
        copy_tree(shared_src, sd_root / "shared")

    shutil.copy2(WEB_UI_ROOT / "portable_host_launcher.py", PORTABLE_ROOT / "portable_host_launcher.py")


def write_scripts() -> None:
    start_stack_ps1 = dedent(
        """$ErrorActionPreference = "Stop"
        Set-Location -Path $PSScriptRoot

        $runRoot = Join-Path $PSScriptRoot "run"
        New-Item -ItemType Directory -Force -Path $runRoot | Out-Null
        $ollamaPidPath = Join-Path $runRoot "ollama.pid"
        $chatterboxPidPath = Join-Path $runRoot "chatterbox.pid"
        $ollamaHealthUrl = "http://127.0.0.1:11434/api/tags"
        $hostHealthUrl = "http://127.0.0.1:8000/api/health"

        function Test-Url([string]$Url, [int]$TimeoutSec = 2) {
          try {
            Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec $TimeoutSec | Out-Null
            return $true
          } catch {
            return $false
          }
        }

        function Wait-Url([string]$Url, [int]$TimeoutSec = 30, [int]$PollMs = 800) {
          $deadline = (Get-Date).AddSeconds($TimeoutSec)
          while ((Get-Date) -lt $deadline) {
            if (Test-Url -Url $Url -TimeoutSec 2) {
              return $true
            }
            Start-Sleep -Milliseconds $PollMs
          }
          return $false
        }

        function Resolve-OllamaExe() {
          try {
            $cmd = Get-Command ollama -ErrorAction SilentlyContinue
            if ($cmd -and $cmd.Source) {
              return $cmd.Source
            }
          } catch {}

          $candidates = @(
            (Join-Path $env:LOCALAPPDATA "Programs\\Ollama\\ollama.exe"),
            (Join-Path $env:ProgramFiles "Ollama\\ollama.exe"),
            (Join-Path ${env:ProgramFiles(x86)} "Ollama\\ollama.exe")
          ) | Where-Object { $_ -and (Test-Path $_) }

          return $candidates | Select-Object -First 1
        }

        function Get-SavedSettings() {
          $settingsPath = Join-Path $PSScriptRoot "data\\robot_settings.json"
          if (-not (Test-Path $settingsPath)) {
            return $null
          }

          try {
            return Get-Content -Path $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
          } catch {
            return $null
          }
        }

        function Needs-LocalOllama($Settings) {
          if (-not $Settings) {
            return $true
          }

          try {
            $urls = @($Settings.ollamaBaseUrl, $Settings.vlmBaseUrl) | Where-Object { $_ -is [string] -and $_.Trim() }
            if (-not $urls -or $urls.Count -eq 0) {
              return $true
            }

            foreach ($url in $urls) {
              if ($url -match '^https?://(127\\.0\\.0\\.1|localhost)(:\\d+)?($|/)') {
                return $true
              }
            }

            return $false
          } catch {
            return $true
          }
        }

        function Needs-LocalChatterbox($Settings) {
          if (-not $Settings) {
            return $false
          }

          $provider = [string]($Settings.ttsProvider)
          if ($provider.Trim().ToLower() -ne "chatterbox") {
            return $false
          }

          $baseUrl = [string]($Settings.chatterboxBaseUrl)
          if (-not $baseUrl.Trim()) {
            return $true
          }

          return $baseUrl -match '^https?://(127\\.0\\.0\\.1|localhost)(:\\d+)?($|/)'
        }

        function Get-ChatterboxBaseUrl($Settings) {
          $baseUrl = [string]($Settings.chatterboxBaseUrl)
          if ($baseUrl.Trim()) {
            return $baseUrl.TrimEnd("/")
          }
          return "http://127.0.0.1:8004"
        }

        function Resolve-ChatterboxRoot($Settings) {
          $candidates = @()

          if ($env:ROBOT_CHATTERBOX_ROOT) {
            $candidates += $env:ROBOT_CHATTERBOX_ROOT
          }

          if ($Settings -and [string]($Settings.chatterboxInstallDir).Trim()) {
            $candidates += [string]($Settings.chatterboxInstallDir).Trim()
          }

          $candidates += @(
            "D:\\robot new version\\Chatterbox-TTS-Server-windows-easyInstallation-main\\Chatterbox-TTS-Server-windows-easyInstallation-main",
            (Join-Path (Split-Path $PSScriptRoot -Parent) "Chatterbox-TTS-Server-windows-easyInstallation-main\\Chatterbox-TTS-Server-windows-easyInstallation-main")
          )

          foreach ($candidate in $candidates | Where-Object { $_ }) {
            $serverPath = Join-Path $candidate "server.py"
            if (Test-Path $serverPath) {
              return (Resolve-Path $candidate).Path
            }
          }

          return $null
        }

        function Resolve-ChatterboxPython([string]$Root) {
          if (-not $Root) {
            return $null
          }

          $venvPython = Join-Path $Root "venv\\Scripts\\python.exe"
          if (Test-Path $venvPython) {
            return $venvPython
          }

          return $null
        }

        function Set-ChatterboxCacheEnvironment([string]$Root) {
          if (-not $Root) {
            return
          }

          $modelCacheRoot = Join-Path $Root "model_cache"
          $hfHome = Join-Path $modelCacheRoot ".hf-home"
          $hfHubCache = Join-Path $hfHome "hub"
          $transformersCache = Join-Path $hfHome "transformers"
          $xdgCacheHome = Join-Path $modelCacheRoot ".xdg-cache"
          $torchHome = Join-Path $modelCacheRoot ".torch"

          $env:HF_HOME = $hfHome
          $env:HUGGINGFACE_HUB_CACHE = $hfHubCache
          $env:TRANSFORMERS_CACHE = $transformersCache
          $env:XDG_CACHE_HOME = $xdgCacheHome
          $env:TORCH_HOME = $torchHome

          New-Item -ItemType Directory -Force -Path $modelCacheRoot, $hfHubCache, $transformersCache, $xdgCacheHome, $torchHome | Out-Null
        }

        function Clear-StalePidFile([string]$Path) {
          if (-not (Test-Path $Path)) {
            return
          }

          try {
            $pidValue = [int](Get-Content -Path $Path -ErrorAction Stop | Select-Object -First 1)
            $process = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
            if (-not $process) {
              Remove-Item -Path $Path -Force -ErrorAction SilentlyContinue
            }
          } catch {
            Remove-Item -Path $Path -Force -ErrorAction SilentlyContinue
          }
        }

        function Get-LanIp() {
          try {
            $defaultRoute = Get-NetRoute -AddressFamily IPv4 -DestinationPrefix "0.0.0.0/0" |
              Sort-Object RouteMetric, InterfaceMetric |
              Select-Object -First 1
            if ($defaultRoute) {
              $addr = Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $defaultRoute.InterfaceIndex |
                Where-Object { $_.IPAddress -ne "127.0.0.1" -and $_.IPAddress -notlike "169.*" } |
                Select-Object -First 1 -ExpandProperty IPAddress
              if ($addr) {
                return $addr
              }
            }
          } catch {
          }

          try {
            return Get-NetIPAddress -AddressFamily IPv4 |
              Where-Object { $_.IPAddress -ne "127.0.0.1" -and $_.IPAddress -notlike "169.*" } |
              Select-Object -First 1 -ExpandProperty IPAddress
          } catch {
            return $null
          }
        }

        $settings = Get-SavedSettings
        Clear-StalePidFile -Path $ollamaPidPath
        Clear-StalePidFile -Path $chatterboxPidPath

        Write-Host ""
        Write-Host "Robot Full Stack Launcher"
        Write-Host "========================="
        Write-Host ""

        if (Needs-LocalOllama $settings) {
          if (Test-Url -Url $ollamaHealthUrl -TimeoutSec 2) {
            Write-Host "Ollama      : already running"
          } else {
            $ollamaExe = Resolve-OllamaExe
            if ($ollamaExe) {
              Write-Host "Ollama      : starting from $ollamaExe"
              try {
                $ollamaProc = Start-Process -FilePath $ollamaExe -ArgumentList "serve" -PassThru -WindowStyle Hidden
                Set-Content -Path $ollamaPidPath -Value $ollamaProc.Id -Encoding UTF8
              } catch {
                Write-Warning "Failed to launch Ollama automatically: $($_.Exception.Message)"
              }

              if (Wait-Url -Url $ollamaHealthUrl -TimeoutSec 25 -PollMs 1000) {
                Write-Host "Ollama      : ready on http://127.0.0.1:11434"
              } else {
                Write-Warning "Ollama did not become ready within the timeout."
              }
            } else {
              Write-Warning "Ollama executable was not found. Host will still start, but AI models may stay degraded."
            }
          }
        } else {
          Write-Host "Ollama      : skipped (current settings use a non-local model endpoint)"
        }

        if (Needs-LocalChatterbox $settings) {
          $chatterboxBaseUrl = Get-ChatterboxBaseUrl $settings
          $chatterboxHealthUrl = "$chatterboxBaseUrl/health"
          if (Test-Url -Url $chatterboxHealthUrl -TimeoutSec 2) {
            Write-Host "Chatterbox  : already running"
          } else {
            $chatterboxRoot = Resolve-ChatterboxRoot $settings
            $chatterboxPython = Resolve-ChatterboxPython $chatterboxRoot
            if ($chatterboxRoot -and $chatterboxPython) {
              Write-Host "Chatterbox  : starting from $chatterboxRoot"
              try {
                Set-ChatterboxCacheEnvironment -Root $chatterboxRoot
                $previousBrowserFlag = $env:CHATTERBOX_OPEN_BROWSER
                $env:CHATTERBOX_OPEN_BROWSER = "0"
                $chatterboxProc = Start-Process -FilePath $chatterboxPython `
                  -ArgumentList "server.py" `
                  -WorkingDirectory $chatterboxRoot `
                  -PassThru `
                  -WindowStyle Hidden
                if ($null -ne $previousBrowserFlag) {
                  $env:CHATTERBOX_OPEN_BROWSER = $previousBrowserFlag
                } else {
                  Remove-Item Env:\\CHATTERBOX_OPEN_BROWSER -ErrorAction SilentlyContinue
                }
                Set-Content -Path $chatterboxPidPath -Value $chatterboxProc.Id -Encoding UTF8
              } catch {
                Write-Warning "Failed to launch Chatterbox automatically: $($_.Exception.Message)"
              }

              if (Wait-Url -Url $chatterboxHealthUrl -TimeoutSec 180 -PollMs 1200) {
                Write-Host "Chatterbox  : ready on $chatterboxBaseUrl"
              } else {
                Write-Warning "Chatterbox did not become ready within the timeout."
              }
            } else {
              Write-Warning "Chatterbox install directory or venv was not found. Set chatterboxInstallDir in settings after running its setup."
            }
          }
        } else {
          Write-Host "Chatterbox  : skipped (provider is not set to chatterbox local)"
        }

        if (Test-Url -Url $hostHealthUrl -TimeoutSec 2) {
          Write-Host "Robot host  : already running"
        } else {
          Write-Host "Robot host  : starting"
          Start-Process -FilePath (Join-Path $PSScriptRoot "start_robot_host.bat") `
            -WorkingDirectory $PSScriptRoot `
            -WindowStyle Minimized | Out-Null

          if (Wait-Url -Url $hostHealthUrl -TimeoutSec 120 -PollMs 1000) {
            Write-Host "Robot host  : ready on http://127.0.0.1:8000"
          } else {
            Write-Warning "Robot host did not become ready within the timeout."
          }
        }

        $health = $null
        try {
          $health = Invoke-RestMethod -Uri $hostHealthUrl -Method Get -TimeoutSec 4
        } catch {}
        $lanIp = Get-LanIp
        Write-Host ""
        Write-Host "Local URL   : http://127.0.0.1:8000"
        if ($health -and $health.host -and $health.host.lanUrl) {
          Write-Host "Mobile URL  : $($health.host.lanUrl)"
        } elseif ($lanIp) {
          Write-Host "Mobile URL  : http://$lanIp`:8000"
        }
        Write-Host ""
        Write-Host "If mobile access is blocked, run allow_mobile_access.bat once as Administrator."
        """
    ).strip() + "\n"

    start_stack_bat = dedent(
        r"""@echo off
        powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_robot_full_stack.ps1"
        echo.
        echo Services were launched. Press any key to close this launcher window...
        pause >nul
        """
    ).strip() + "\n"

    start_bat = dedent(
        r"""@echo off
        setlocal
        cd /d "%~dp0"
        set "ROBOT_APP_ROOT=%~dp0"
        set "ROBOT_HOST=0.0.0.0"
        set "ROBOT_PORT=8000"
        set "ROBOT_HOST_MODE=auto"
        set "ROBOT_PID_PATH=%~dp0run\robot_host.pid"
        set "PYTHON_BIN=%~dp0runtime\python.exe"
        set "PROJECT_VENV=%~dp0..\..\..\.venv\Scripts\python.exe"
        if exist "%PROJECT_VENV%" set "PYTHON_BIN=%PROJECT_VENV%"
        echo.
        echo Robot Control Host starting...
        echo Local:   http://127.0.0.1:8000
        for /f %%I in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne '127.0.0.1' -and $_.IPAddress -notlike '169.*' } | Select-Object -First 1 -ExpandProperty IPAddress)"') do set "HOST_IP=%%I"
        if defined HOST_IP echo Mobile:  http://%HOST_IP%:8000
        echo Python:  %PYTHON_BIN%
        echo.
        "%PYTHON_BIN%" "%~dp0portable_host_launcher.py"
        endlocal
        """
    ).strip() + "\n"

    start_ps1 = dedent(
        """$ErrorActionPreference = "Stop"
        Set-Location -Path $PSScriptRoot
        $env:ROBOT_APP_ROOT = $PSScriptRoot
        $env:ROBOT_HOST = "0.0.0.0"
        $env:ROBOT_PORT = "8000"
        $env:ROBOT_HOST_MODE = "auto"
        $env:ROBOT_PID_PATH = Join-Path $PSScriptRoot "run\\robot_host.pid"
        $pythonExe = Join-Path $PSScriptRoot "runtime\\python.exe"
        $projectPython = Join-Path $PSScriptRoot "..\\..\\..\\.venv\\Scripts\\python.exe"
        if (Test-Path $projectPython) {
          $pythonExe = (Resolve-Path $projectPython).Path
        }
        Write-Host ""
        Write-Host "Robot Control Host starting..."
        Write-Host "Local:   http://127.0.0.1:8000"
        try {
          $ip = Get-NetIPAddress -AddressFamily IPv4 |
            Where-Object { $_.IPAddress -ne "127.0.0.1" -and $_.IPAddress -notlike "169.*" } |
            Select-Object -First 1 -ExpandProperty IPAddress
          if ($ip) {
            Write-Host "Mobile:  http://$ip`:8000"
          }
        } catch {}
        Write-Host "Python:  $pythonExe"
        Write-Host ""
        & $pythonExe "$PSScriptRoot\\portable_host_launcher.py"
        """
    ).strip() + "\n"

    stop_ps1 = dedent(
        """$ErrorActionPreference = "Stop"
        $pidFile = Join-Path $PSScriptRoot "run\\robot_host.pid"
        $stopped = $false

        if (Test-Path $pidFile) {
          try {
            $pidValue = [int](Get-Content -Path $pidFile -ErrorAction Stop | Select-Object -First 1)
            Stop-Process -Id $pidValue -Force -ErrorAction Stop
            $stopped = $true
          } catch {}
          Remove-Item -Path $pidFile -Force -ErrorAction SilentlyContinue
        }

        if (-not $stopped) {
          try {
            $processes = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
              Where-Object { $_.CommandLine -like "*portable_host_launcher.py*" }
            foreach ($process in $processes) {
              Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
              $stopped = $true
            }
          } catch {}
        }

        if ($stopped) {
          Write-Host "Robot Control Host stopped."
        } else {
          Write-Host "Robot Control Host is not running."
        }
        """
    ).strip() + "\n"

    stop_stack_ps1 = dedent(
        """$ErrorActionPreference = "Stop"
        $runRoot = Join-Path $PSScriptRoot "run"
        $ollamaPidPath = Join-Path $runRoot "ollama.pid"
        $chatterboxPidPath = Join-Path $runRoot "chatterbox.pid"

        & "$PSScriptRoot\\stop_robot_host.ps1"

        $ollamaStopped = $false
        if (Test-Path $ollamaPidPath) {
          try {
            $pidValue = [int](Get-Content -Path $ollamaPidPath -ErrorAction Stop | Select-Object -First 1)
            Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
            $ollamaStopped = $true
          } catch {}
          Remove-Item -Path $ollamaPidPath -Force -ErrorAction SilentlyContinue
        }

        if ($ollamaStopped) {
          Write-Host "Managed Ollama instance stopped."
        } else {
          Write-Host "No managed Ollama instance was started by this bundle."
        }

        $chatterboxStopped = $false
        if (Test-Path $chatterboxPidPath) {
          try {
            $pidValue = [int](Get-Content -Path $chatterboxPidPath -ErrorAction Stop | Select-Object -First 1)
            Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
            $chatterboxStopped = $true
          } catch {}
          Remove-Item -Path $chatterboxPidPath -Force -ErrorAction SilentlyContinue
        }

        if ($chatterboxStopped) {
          Write-Host "Managed Chatterbox instance stopped."
        } else {
          Write-Host "No managed Chatterbox instance was started by this bundle."
        }
        """
    ).strip() + "\n"

    stop_bat = dedent(
        r"""@echo off
        powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_robot_host.ps1"
        """
    ).strip() + "\n"

    stop_stack_bat = dedent(
        r"""@echo off
        powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_robot_full_stack.ps1"
        """
    ).strip() + "\n"

    health_ps1 = dedent(
        """$ErrorActionPreference = "Stop"
        $healthUrl = "http://127.0.0.1:8000/api/health"
        try {
          $response = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 3
          Write-Host "success : $($response.success)"
          Write-Host "ready   : $($response.ready)"
          Write-Host "degraded: $($response.degraded)"
          if ($response.host -and $response.host.mode) {
            Write-Host "mode    : $($response.host.mode)"
          }
          if ($response.host -and $response.host.lanUrl) {
            Write-Host "mobile  : $($response.host.lanUrl)"
          }
          if ($response.message) {
            Write-Host "message : $($response.message)"
          }
          exit 0
        } catch {
          Write-Host "Health check failed: $($_.Exception.Message)"
          exit 1
        }
        """
    ).strip() + "\n"

    health_bat = dedent(
        r"""@echo off
        powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0check_robot_host.ps1"
        """
    ).strip() + "\n"

    firewall_ps1 = dedent(
        """$ErrorActionPreference = "Stop"
        $ruleName = "Robot Control Host 8000"
        $existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
        if (-not $existing) {
          New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 | Out-Null
          Write-Host "Firewall rule created for TCP 8000."
        } else {
          Write-Host "Firewall rule already exists."
        }
        """
    ).strip() + "\n"

    firewall_bat = dedent(
        r"""@echo off
        powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0allow_mobile_access.ps1"
        """
    ).strip() + "\n"

    readme = dedent(
        """RobotControlHost portable bundle
        =================================

        1. Copy this whole folder to the target Windows machine.
        2. Recommended: run start_robot_full_stack.bat
           This starts Ollama, Chatterbox (if configured), and the robot host together.
        3. Or run start_robot_host.bat / start_robot_host.ps1
           if you want only the host without the Ollama helper.
        4. Open from the phone on the same network:
           http://<host-ip>:8000
        5. Optional helpers:
           - stop_robot_full_stack.bat
           - stop_robot_host.bat
           - check_robot_host.bat
           - allow_mobile_access.bat

        Notes
        -----
        - If the phone cannot reach the page, run allow_mobile_access.bat once as Administrator.
        - This bundle already includes Python and backend dependencies.
        - Frontend files are prebuilt under dist/.
        - Host mode defaults to auto detection and works for laptop host or mini PC host.
        - start_robot_full_stack.bat will try to launch a local Ollama instance automatically
          if the saved settings point to 127.0.0.1 or localhost.
        - If TTS provider is set to chatterbox local, the launcher will also try to start
          the local Chatterbox server using chatterboxInstallDir from settings.
        - Ollama itself is not bundled here. The target machine still needs Ollama installed
          if you want local LLM/VLM features.
        - Chatterbox itself is not bundled here. Install it locally and set chatterboxInstallDir
          in settings if you want offline local TTS.
        """
    ).strip() + "\n"

    (PORTABLE_ROOT / "start_robot_full_stack.ps1").write_text(start_stack_ps1, encoding="utf-8")
    (PORTABLE_ROOT / "start_robot_full_stack.bat").write_text(start_stack_bat, encoding="utf-8", newline="\r\n")
    (PORTABLE_ROOT / "start_robot_host.bat").write_text(start_bat, encoding="utf-8", newline="\r\n")
    (PORTABLE_ROOT / "start_robot_host.ps1").write_text(start_ps1, encoding="utf-8")
    (PORTABLE_ROOT / "stop_robot_host.ps1").write_text(stop_ps1, encoding="utf-8")
    (PORTABLE_ROOT / "stop_robot_host.bat").write_text(stop_bat, encoding="utf-8", newline="\r\n")
    (PORTABLE_ROOT / "stop_robot_full_stack.ps1").write_text(stop_stack_ps1, encoding="utf-8")
    (PORTABLE_ROOT / "stop_robot_full_stack.bat").write_text(stop_stack_bat, encoding="utf-8", newline="\r\n")
    (PORTABLE_ROOT / "check_robot_host.ps1").write_text(health_ps1, encoding="utf-8")
    (PORTABLE_ROOT / "check_robot_host.bat").write_text(health_bat, encoding="utf-8", newline="\r\n")
    (PORTABLE_ROOT / "allow_mobile_access.ps1").write_text(firewall_ps1, encoding="utf-8")
    (PORTABLE_ROOT / "allow_mobile_access.bat").write_text(firewall_bat, encoding="utf-8", newline="\r\n")
    (PORTABLE_ROOT / "README.txt").write_text(readme, encoding="utf-8")


def create_zip() -> None:
    ZIP_PATH.parent.mkdir(parents=True, exist_ok=True)
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()

    with ZipFile(ZIP_PATH, "w", compression=ZIP_DEFLATED, compresslevel=6) as zip_file:
        for file_path in PORTABLE_ROOT.rglob("*"):
            if file_path.is_file():
                zip_file.write(file_path, file_path.relative_to(PORTABLE_ROOT.parent))


def main() -> None:
    PORTABLE_ROOT.parent.mkdir(parents=True, exist_ok=True)
    run(["npm", "run", "build"], cwd=WEB_UI_ROOT)
    clean_dir(PORTABLE_ROOT)
    clean_dir(RUNTIME_ROOT)
    copy_python_runtime()
    install_python_packages()
    copy_application_files()
    write_scripts()
    create_zip()
    print(f"Portable bundle ready: {PORTABLE_ROOT}")
    print(f"Zip archive ready: {ZIP_PATH}")


if __name__ == "__main__":
    main()

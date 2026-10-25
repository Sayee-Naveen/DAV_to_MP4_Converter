"""
DAV to MP4 Converter - High Performance Backend Engine
Supports Multi-core Multi-threading, Hardware Acceleration (Intel QSV / MediaFoundation),
Lightning Fast Stream Remuxing, and Concurrent Batch Processing.
"""

import os
import sys
import re
import subprocess
import threading
import time
from typing import Callable, Optional, Dict, Any, List

def get_ffmpeg_path() -> str:
    """Finds the FFmpeg executable."""
    # 1. Bundled in PyInstaller
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        bundle_bin = os.path.join(sys._MEIPASS, 'bin', 'ffmpeg.exe')
        if os.path.isfile(bundle_bin):
            return bundle_bin
        bundle_root = os.path.join(sys._MEIPASS, 'ffmpeg.exe')
        if os.path.isfile(bundle_root):
            return bundle_root

    # 2. Local directory bin/ffmpeg.exe
    base_dir = os.path.dirname(os.path.abspath(__file__))
    local_bin = os.path.join(base_dir, 'bin', 'ffmpeg.exe')
    if os.path.isfile(local_bin):
        return local_bin

    # 3. Try imageio_ffmpeg
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.isfile(exe):
            return exe
    except Exception:
        pass

    # 4. System PATH
    import shutil
    path_exe = shutil.which('ffmpeg')
    if path_exe:
        return path_exe

    raise FileNotFoundError("FFmpeg executable could not be found.")

def get_vlc_path() -> Optional[str]:
    """Finds VLC media player executable on the Windows system."""
    candidates = [
        r"C:\Program Files\VideoLAN\VLC\vlc.exe",
        r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\VideoLAN\VLC\vlc.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\VideoLAN\VLC\vlc.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    import shutil
    return shutil.which('vlc')

def parse_duration_to_seconds(time_str: str) -> float:
    """Converts HH:MM:SS.ms to total seconds."""
    try:
        parts = time_str.strip().split(':')
        if len(parts) == 3:
            h = float(parts[0])
            m = float(parts[1])
            s = float(parts[2])
            return h * 3600 + m * 60 + s
    except Exception:
        pass
    return 0.0

def probe_file_info(file_path: str, ffmpeg_path: str) -> Dict[str, Any]:
    """
    Probes media information using FFmpeg.
    Also detects stored resolution and computes the correct display aspect ratio
    so that converted MP4 files always display at the right proportions in VLC.
    """
    from math import gcd

    info = {
        'duration_sec': 0.0,
        'duration_str': 'Unknown',
        'resolution': 'Unknown',
        'codec': 'Unknown',
        'fps': 'Unknown',
        'width': 0,
        'height': 0,
        'dar': '',       # e.g. "8:9" or "16:9"
        'sar': '',       # e.g. "1:1"
        'aspect_arg': '' # ready-to-use -aspect value
    }

    startupinfo = None
    creationflags = 0
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creationflags = subprocess.CREATE_NO_WINDOW

    # First probe without forcing demuxer, then with dhav if needed
    for force_dhav in (False, True):
        cmd = [ffmpeg_path, '-hide_banner']
        if force_dhav:
            cmd.extend(['-f', 'dhav'])
        cmd.extend(['-i', file_path])
        try:
            p = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                startupinfo=startupinfo,
                creationflags=creationflags,
                timeout=10
            )
            output = p.stderr

            dur_match = re.search(r'Duration:\s*(\d+:\d+:\d+\.\d+)', output)
            if dur_match:
                info['duration_str'] = dur_match.group(1).split('.')[0]
                info['duration_sec'] = parse_duration_to_seconds(dur_match.group(1))

            # Match resolution and optionally SAR/DAR
            # Example: "Video: hevc (Main), yuv420p(tv), 960x1080, 25 fps"
            # Example: "Video: h264, yuv420p, 1920x1080 [SAR 1:1 DAR 16:9], 30 fps"
            vid_match = re.search(
                r'Stream #\d+:\d+.*?Video:\s*([a-zA-Z0-9_\-]+).*?(\d{3,5})x(\d{3,5})'
                r'(?:\s*\[SAR\s*(\d+):(\d+)\s+DAR\s*(\d+):(\d+)\])?',
                output
            )
            if vid_match:
                info['codec'] = vid_match.group(1)
                w = int(vid_match.group(2))
                h = int(vid_match.group(3))
                info['width'] = w
                info['height'] = h
                info['resolution'] = f"{w}x{h}"

                if vid_match.group(6) and vid_match.group(7):
                    # DAR already embedded in file
                    dar_n = int(vid_match.group(6))
                    dar_d = int(vid_match.group(7))
                    info['dar'] = f"{dar_n}:{dar_d}"
                    info['sar'] = f"{vid_match.group(4)}:{vid_match.group(5)}"
                    info['aspect_arg'] = f"{dar_n}:{dar_d}"
                else:
                    # No DAR in file — compute from stored resolution (assume square pixels)
                    g = gcd(w, h)
                    dar_n = w // g
                    dar_d = h // g
                    info['dar'] = f"{dar_n}:{dar_d}"
                    info['sar'] = "1:1"
                    info['aspect_arg'] = f"{dar_n}:{dar_d}"

            fps_match = re.search(r'(\d+(?:\.\d+)?)\s*fps', output)
            if fps_match:
                info['fps'] = f"{fps_match.group(1)} fps"

            if info['width'] > 0:
                break  # Got what we need
        except Exception:
            continue

    return info

class ConversionTask:
    def __init__(self, input_path: str, output_path: str, preset: str = "Lightning Remux (Lossless, Instant - Recommended)", aspect_ratio: str = "16:9"):
        self.input_path = input_path
        self.output_path = output_path
        self.preset = preset
        self.aspect_ratio = aspect_ratio
        self.status = "Pending"  # Pending, Converting, Completed, Failed, Cancelled
        self.progress = 0.0      # 0.0 to 1.0
        self.speed = ""
        self.time_str = "00:00:00"
        self.error_msg = ""
        self.total_duration_sec = 0.0
        self.file_size_str = self._format_size(input_path)
        
    @staticmethod
    def _format_size(path: str) -> str:
        try:
            sz = os.path.getsize(path)
            for unit in ['B', 'KB', 'MB', 'GB']:
                if sz < 1024.0:
                    return f"{sz:.1f} {unit}"
                sz /= 1024.0
            return f"{sz:.1f} TB"
        except Exception:
            return "0 B"

class DAVConverter:
    """High-performance multi-threaded conversion engine."""

    PRESETS = {
        "Lightning Remux (Lossless, Instant - Recommended)": {
            "desc": "Transfers existing H.264/H.265 stream directly into MP4 without re-encoding. 100x-300x faster (takes 2-5 seconds). Lossless quality.",
            "mode": "remux",
            "video_codec": "copy",
            "audio_codec": "aac",
            "extra_args": ["-movflags", "+faststart"]
        },
        "GPU Hardware Accelerated (Intel QuickSync / MF)": {
            "desc": "Encodes on Intel UHD 620 GPU hardware chip. Super fast, zero CPU lag.",
            "mode": "hw_mf",
            "video_codec": "h264_mf",
            "extra_args": ["-b:v", "4M", "-c:a", "aac", "-movflags", "+faststart"]
        },
        "Multi-Threaded Fast Re-encode (All CPU Cores)": {
            "desc": "Re-encodes video using all 8 logical CPU threads at ultrafast speed. Fixes corrupted timestamps.",
            "mode": "reencode_fast",
            "video_codec": "libx264",
            "crf": "22",
            "preset": "ultrafast",
            "audio_codec": "aac",
            "threads": "0",
            "extra_args": ["-pix_fmt", "yuv420p", "-movflags", "+faststart"]
        },
        "Balanced Quality Re-encode (H.264 / Multi-threaded)": {
            "desc": "High compatibility H.264 with veryfast multi-core encoding.",
            "mode": "reencode_std",
            "video_codec": "libx264",
            "crf": "22",
            "preset": "veryfast",
            "audio_codec": "aac",
            "threads": "0",
            "extra_args": ["-pix_fmt", "yuv420p", "-movflags", "+faststart"]
        },
        "Force DHAV Demuxer (Surveillance Fix)": {
            "desc": "Forces Dahua DHAV demuxer. Best for damaged or proprietary CCTV recordings.",
            "mode": "dhav",
            "video_codec": "copy",
            "audio_codec": "aac",
            "extra_args": ["-movflags", "+faststart"]
        },
        "H.265 / HEVC MP4 (High Compression)": {
            "desc": "High efficiency HEVC/H.265 with all CPU threads active.",
            "mode": "hevc",
            "video_codec": "libx265",
            "crf": "26",
            "preset": "ultrafast",
            "audio_codec": "aac",
            "threads": "0",
            "extra_args": ["-pix_fmt", "yuv420p", "-movflags", "+faststart"]
        }
    }

    def __init__(self):
        self.ffmpeg_path = get_ffmpeg_path()
        self.vlc_path = get_vlc_path()
        self._running_processes: Dict[str, subprocess.Popen] = {}
        self._proc_lock = threading.Lock()
        self._stop_flag = False

    def build_command(self, task: ConversionTask, strategy: str = "primary",
                      aspect_arg: str = "") -> List[str]:
        """Constructs the optimized FFmpeg command line with correct aspect ratio."""
        preset_info = self.PRESETS.get(task.preset, self.PRESETS["Lightning Remux (Lossless, Instant - Recommended)"])
        cmd = [self.ffmpeg_path, "-y", "-hide_banner"]

        # Strategy-specific input flags
        if strategy == "dhav" or preset_info["mode"] == "dhav":
            cmd.extend(["-f", "dhav"])
        elif strategy == "h264_raw":
            cmd.extend(["-f", "h264"])
        elif strategy == "genpts":
            cmd.extend(["-fflags", "+genpts"])

        cmd.extend(["-i", task.input_path])

        # Encoders and thread allocation
        if preset_info["mode"] == "remux" and strategy == "primary":
            # Instant lossless copy
            cmd.extend(["-c:v", "copy", "-c:a", "aac"])
        elif preset_info["mode"] == "hw_mf":
            # Hardware MediaFoundation encoder
            cmd.extend([
                "-c:v", "h264_mf",
                "-b:v", "4M",
                "-c:a", "aac"
            ])
        elif preset_info["mode"] == "hevc":
            cmd.extend([
                "-threads", "0",
                "-c:v", "libx265",
                "-crf", preset_info["crf"],
                "-preset", preset_info["preset"],
                "-c:a", "aac",
                "-b:a", "128k"
            ])
        elif strategy == "primary":
            # Software re-encode with all CPU threads
            cmd.extend([
                "-threads", "0",
                "-c:v", preset_info.get("video_codec", "libx264"),
                "-crf", preset_info.get("crf", "22"),
                "-preset", preset_info.get("preset", "ultrafast"),
                "-c:a", "aac",
                "-b:a", "128k"
            ])
        else:
            # Fallback strategy: fast multi-threaded re-encode
            cmd.extend([
                "-threads", "0",
                "-c:v", "libx264",
                "-crf", "22",
                "-preset", "ultrafast",
                "-c:a", "aac"
            ])

        # Inject the correct display aspect ratio so VLC renders at proper proportions
        if aspect_arg:
            cmd.extend(["-aspect", aspect_arg])

        cmd.extend(preset_info.get("extra_args", ["-pix_fmt", "yuv420p", "-movflags", "+faststart"]))
        cmd.append(task.output_path)
        return cmd

    def convert_single(self, task: ConversionTask, log_callback: Optional[Callable[[str], None]] = None) -> bool:
        """
        Converts a single DAV file with multi-tier automatic fallback.
        """
        task.status = "Converting"
        task.progress = 0.0

        if log_callback:
            log_callback(f"Starting conversion: {os.path.basename(task.input_path)} [{task.preset}]")

        info = probe_file_info(task.input_path, self.ffmpeg_path)
        task.total_duration_sec = info['duration_sec']
        
        # Determine aspect ratio: use task setting if specified, otherwise probe detection
        user_aspect = getattr(task, 'aspect_ratio', '')
        if user_aspect and user_aspect.lower() not in ('auto', 'default', ''):
            aspect_arg = user_aspect
        else:
            aspect_arg = info.get('aspect_arg', '')

        if log_callback:
            if info['duration_sec'] > 0:
                log_callback(f"Duration: {info['duration_str']} ({info['duration_sec']:.1f}s), Codec: {info['codec']}, Res: {info['resolution']}")
            if aspect_arg:
                log_callback(f"Setting display aspect ratio: {aspect_arg}")

        preset_info = self.PRESETS.get(task.preset, self.PRESETS["Lightning Remux (Lossless, Instant - Recommended)"])
        
        # Determine strategies
        strategies = ["primary"]
        if preset_info["mode"] == "remux":
            # If remux fails, automatically fallback to forced dhav copy, then multi-threaded re-encode
            strategies.extend(["dhav", "reencode_fallback"])
        else:
            strategies.extend(["dhav", "genpts", "h264_raw"])

        success = False
        last_error = ""

        out_dir = os.path.dirname(os.path.abspath(task.output_path))
        os.makedirs(out_dir, exist_ok=True)

        for attempt_idx, strat in enumerate(strategies):
            if self._stop_flag:
                task.status = "Cancelled"
                return False

            cmd = self.build_command(task, strategy=strat, aspect_arg=aspect_arg)
            if log_callback:
                log_callback(f"Running mode '{strat}' (Attempt {attempt_idx+1}/{len(strategies)})")
                log_callback("CMD: " + " ".join(cmd))

            startupinfo = None
            creationflags = 0
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                creationflags = subprocess.CREATE_NO_WINDOW

            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    encoding='utf-8',
                    errors='replace',
                    startupinfo=startupinfo,
                    creationflags=creationflags
                )

                with self._proc_lock:
                    self._running_processes[task.input_path] = proc

                time_pattern = re.compile(r'time=(\d+:\d+:\d+\.\d+)')
                speed_pattern = re.compile(r'speed=\s*([\d\.]+x)')

                for line in proc.stderr:
                    if self._stop_flag:
                        proc.kill()
                        task.status = "Cancelled"
                        return False

                    time_match = time_pattern.search(line)
                    if time_match:
                        cur_time_str = time_match.group(1)
                        task.time_str = cur_time_str.split('.')[0]
                        cur_sec = parse_duration_to_seconds(cur_time_str)
                        if task.total_duration_sec > 0:
                            task.progress = min(0.99, cur_sec / task.total_duration_sec)
                        else:
                            task.progress = min(0.95, (task.progress + 0.04) if task.progress < 0.95 else 0.95)

                    speed_match = speed_pattern.search(line)
                    if speed_match:
                        task.speed = speed_match.group(1)

                proc.wait()
                retcode = proc.returncode

                with self._proc_lock:
                    if task.input_path in self._running_processes:
                        del self._running_processes[task.input_path]

                file_ok = os.path.isfile(task.output_path) and os.path.getsize(task.output_path) > 1024

                if retcode == 0 and file_ok:
                    success = True
                    task.progress = 1.0
                    task.status = "Completed"
                    if log_callback:
                        log_callback(f"[SUCCESS] Converted to {os.path.basename(task.output_path)} ({task._format_size(task.output_path)})")
                    break
                else:
                    last_error = f"Exit code: {retcode}, Output valid: {file_ok}"
                    if log_callback:
                        log_callback(f"Mode '{strat}' failed: {last_error}")
                    if os.path.isfile(task.output_path) and not file_ok:
                        try:
                            os.remove(task.output_path)
                        except Exception:
                            pass

            except Exception as e:
                last_error = str(e)
                if log_callback:
                    log_callback(f"Exception during mode '{strat}': {e}")

        if not success:
            task.status = "Failed"
            task.error_msg = last_error
            if log_callback:
                log_callback(f"[ERROR] Failed to convert {os.path.basename(task.input_path)}: {last_error}")

        return success

    def stop(self):
        """Cancels all active conversions immediately."""
        self._stop_flag = True
        with self._proc_lock:
            for p in list(self._running_processes.values()):
                try:
                    p.terminate()
                    p.kill()
                except Exception:
                    pass
            self._running_processes.clear()

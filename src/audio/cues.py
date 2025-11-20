"""Audio cue utilities for KLoROS."""

import os
import shutil
import subprocess
from typing import Optional


def play_wake_chime(sound_file: Optional[str] = None):
    """Play wake word confirmation chime.
    
    Args:
        sound_file: Path to sound file (default: freedesktop dialog-information)
    """
    print("[wake-chime] Function called")
    
    # Check if muted/disabled
    if os.getenv("KLR_WAKE_CHIME_ENABLED", "1") == "0":
        print("[wake-chime] Disabled by environment")
        return
    
    # Find paplay utility
    paplay = shutil.which("paplay")
    if not paplay:
        print("[wake-chime] paplay not found")
        return
    
    print(f"[wake-chime] Found paplay at {paplay}")
    
    # Use provided sound or default
    if sound_file is None:
        sound_file = os.getenv(
            "KLR_WAKE_CHIME_FILE",
            "/usr/share/sounds/freedesktop/stereo/dialog-information.oga"
        )
    
    print(f"[wake-chime] Using sound file: {sound_file}")
    
    # Check if sound file exists
    if not os.path.exists(sound_file):
        print(f"[wake-chime] Sound file not found: {sound_file}")
        # Try alternate paths
        alternates = [
            "/usr/share/sounds/freedesktop/stereo/bell.oga",
            "/usr/share/sounds/freedesktop/stereo/message.oga",
            "/usr/share/sounds/ubuntu/stereo/dialog-information.ogg",
        ]
        for alt in alternates:
            if os.path.exists(alt):
                sound_file = alt
                print(f"[wake-chime] Using alternate: {sound_file}")
                break
        else:
            print("[wake-chime] No alternate sound files found")
            return
    
    # Play sound with user's PipeWire session
    try:
        env = os.environ.copy()
        
        # Use playback user's runtime dir if specified (for cross-user audio)
        playback_runtime = os.getenv("KLR_PLAYBACK_USER_RUNTIME")
        if playback_runtime:
            env["XDG_RUNTIME_DIR"] = playback_runtime
            env["PULSE_RUNTIME_PATH"] = f"{playback_runtime}/pulse"
            print(f"[wake-chime] Using playback runtime: {playback_runtime}")
        elif "XDG_RUNTIME_DIR" not in env:
            env["XDG_RUNTIME_DIR"] = "/run/user/1001"
            env["PULSE_RUNTIME_PATH"] = "/run/user/1001/pulse"
        
        print(f"[wake-chime] Playing with XDG_RUNTIME_DIR={env.get('XDG_RUNTIME_DIR')}")
        
        proc = subprocess.Popen(
            [paplay, sound_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env
        )
        
        print(f"[wake-chime] Subprocess started with PID {proc.pid}")
        
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        print(f"[wake-chime] Failed to play: {e}")

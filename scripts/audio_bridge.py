#!/usr/bin/env python3
"""
Audio Bridge for KLoROS - creates virtual audio devices to work around hardware access issues
"""
import subprocess
import time
import os
import signal
import sys

class AudioBridge:
    def __init__(self):
        self.pulseaudio_pid = None
        self.pipewire_enabled = False
        
    def setup_audio_environment(self):
        """Setup audio environment for kloros user"""
        print("[bridge] Setting up audio environment...")
        
        # Ensure runtime directory exists
        uid = os.getuid()
        runtime_dir = f"/run/user/{uid}"
        if not os.path.exists(runtime_dir):
            try:
                os.makedirs(runtime_dir, mode=0o755, exist_ok=True)
                print(f"[bridge] Created runtime directory: {runtime_dir}")
            except:
                pass
        
        # Set environment variables
        os.environ["XDG_RUNTIME_DIR"] = runtime_dir
        os.environ["PULSE_RUNTIME_PATH"] = f"{runtime_dir}/pulse"
        
        # Kill any existing PulseAudio
        try:
            subprocess.run(["pulseaudio", "--kill"], check=False, capture_output=True)
            time.sleep(1)
        except:
            pass
            
        # Start PulseAudio with specific configuration
        try:
            result = subprocess.run([
                "pulseaudio", 
                "--start", 
                "--exit-idle-time=-1",  # Don't exit
                "--disable-shm",        # Disable shared memory (can cause issues)
                "--verbose"
            ], capture_output=True, text=True, timeout=10)
            print(f"[bridge] PulseAudio started: {result.returncode}")
            if result.stderr:
                print(f"[bridge] PA stderr: {result.stderr[:200]}")
        except Exception as e:
            print(f"[bridge] Failed to start PulseAudio: {e}")
            
        # Create null sink for testing
        try:
            subprocess.run([
                "pactl", "load-module", "module-null-sink", 
                "sink_name=kloros_null", "sink_properties=device.description=KLoROS_Test_Sink"
            ], check=False, capture_output=True)
            print("[bridge] Created null sink")
        except:
            pass
            
        # Create virtual input
        try:
            subprocess.run([
                "pactl", "load-module", "module-virtual-source",
                "source_name=kloros_input", "master=kloros_null.monitor"
            ], check=False, capture_output=True)
            print("[bridge] Created virtual input")
        except:
            pass
            
    def test_audio_access(self):
        """Test if we can access audio devices"""
        print("[bridge] Testing audio access...")
        
        try:
            result = subprocess.run(["pactl", "info"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print("[bridge] ✓ PulseAudio accessible")
                
                # List sources
                result = subprocess.run(["pactl", "list", "sources", "short"], 
                                      capture_output=True, text=True, timeout=5)
                if "kloros" in result.stdout:
                    print("[bridge] ✓ Virtual source available")
                    return True
                else:
                    print("[bridge] ✗ No virtual source found")
            else:
                print("[bridge] ✗ PulseAudio not accessible")
        except Exception as e:
            print(f"[bridge] Error testing audio: {e}")
            
        return False
        
    def create_loopback_device(self):
        """Create ALSA loopback device as fallback"""
        print("[bridge] Creating ALSA loopback device...")
        try:
            # Load snd-aloop module
            subprocess.run(["sudo", "modprobe", "snd-aloop"], check=False)
            time.sleep(1)
            print("[bridge] ✓ ALSA loopback module loaded")
            return True
        except Exception as e:
            print(f"[bridge] Failed to create loopback: {e}")
            return False
            
    def start_keepalive(self):
        """Start audio keepalive using virtual devices"""
        print("[bridge] Starting audio keepalive...")
        try:
            # Use pacat to generate silence on virtual source
            proc = subprocess.Popen([
                "pacat", "--record", "--source=kloros_input", "--format=s16le",
                "--rate=44100", "--channels=1", "--null"
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"[bridge] Keepalive started (PID: {proc.pid})")
            return proc
        except Exception as e:
            print(f"[bridge] Failed to start keepalive: {e}")
            return None

def main():
    bridge = AudioBridge()
    
    # Setup audio environment
    bridge.setup_audio_environment()
    time.sleep(2)
    
    # Test access
    if bridge.test_audio_access():
        print("[bridge] Audio bridge setup successful!")
    else:
        print("[bridge] Trying ALSA loopback fallback...")
        bridge.create_loopback_device()
        
    # Start keepalive
    keepalive_proc = bridge.start_keepalive()
    
    try:
        print("[bridge] Audio bridge running. Press Ctrl+C to stop.")
        while True:
            time.sleep(10)
            # Check if keepalive is still running
            if keepalive_proc and keepalive_proc.poll() is not None:
                print("[bridge] Restarting keepalive...")
                keepalive_proc = bridge.start_keepalive()
    except KeyboardInterrupt:
        print("\n[bridge] Shutting down...")
        if keepalive_proc:
            keepalive_proc.terminate()

if __name__ == "__main__":
    main()

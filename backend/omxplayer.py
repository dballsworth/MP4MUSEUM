# mp4museum - OMXPlayer Alternative (No VLC threading issues)
# Use omxplayer instead of VLC to avoid threading problems

import sys
import os
import subprocess
import time
import signal
import atexit
import threading
from threading import Thread, Event, Lock

print("🎬 mp4museum - OMXPlayer Alternative")
print("🚀 Using omxplayer instead of VLC to avoid threading issues")

# Global state
running = True
shutdown_event = Event()
collection_lock = Lock()
current_player_process = None

# Playback state management
playback_state = "stopped"  # "playing", "paused", "stopped"
playback_state_lock = Lock()
force_stop_playback = Event()  # Signal to stop the entire playlist

# Flask imports
from flask import Flask, jsonify, request
from flask_cors import CORS

# Collection management - will be set after finding media
media_base_path = "/media/internal"
available_collections = []
current_collection = "/media/internal"
current_collection_id = 0
collection_changed = False
last_collection = None
last_collection_id = -1

def debug_thread_info():
    """Print current thread information"""
    thread_count = threading.active_count()
    print(f"🧵 Active threads: {thread_count}")
    for thread in threading.enumerate():
        print(f"   - {thread.name}")
    sys.stdout.flush()

def get_collections():
    """Get available collections - check multiple possible locations"""
    possible_bases = [
        "/media/internal",
        "/media/videos", 
        "/media",
        "/home/pi/videos"
    ]
    
    print("🔍 Searching for collections in:")
    for base in possible_bases:
        print(f"   Checking: {base}")
        if os.path.exists(base):
            try:
                # Check for subdirectories (collections) - ignore hidden files/dirs
                subdirs = []
                for item in os.listdir(base):
                    # Skip hidden files/directories (starting with .)
                    if item.startswith('.'):
                        continue
                    full_path = os.path.join(base, item)
                    if os.path.isdir(full_path):
                        subdirs.append(item)
                
                if subdirs:
                    print(f"   ✅ Found {len(subdirs)} collections in {base}: {sorted(subdirs)}")
                    return base, sorted(subdirs)
                
                # Check for video files directly in this directory (also ignore hidden)
                videos = []
                for item in os.listdir(base):
                    if item.startswith('.'):
                        continue
                    if item.lower().endswith(('.mp4', '.avi', '.mkv', '.mov', '.m4v')):
                        videos.append(item)
                
                if videos:
                    print(f"   ✅ Found {len(videos)} videos directly in {base}")
                    return base, ['default']  # Create a default collection
                    
                print(f"   📁 {base} exists but no videos/collections found")
            except Exception as e:
                print(f"   ❌ Error reading {base}: {e}")
        else:
            print(f"   ❌ {base} doesn't exist")
    
    print("   ⚠️ No collections found anywhere!")
    return "/media/internal", []

def get_playlist_files(collection_path):
    """Get video files from collection - handle both direct files and subdirectories"""
    try:
        if not os.path.exists(collection_path):
            print(f"❌ Collection path doesn't exist: {collection_path}")
            return []
        
        files = []
        
        # If this is a 'default' collection, look for files directly in the base directory
        if os.path.basename(collection_path) == 'default':
            collection_path = os.path.dirname(collection_path)
        
        print(f"📁 Scanning for videos in: {collection_path}")
        
        for item in os.listdir(collection_path):
            # Skip hidden files (starting with .) - these are often macOS metadata files
            if item.startswith('.'):
                continue
                
            full_path = os.path.join(collection_path, item)
            if os.path.isfile(full_path):
                if item.lower().endswith(('.mp4', '.avi', '.mkv', '.mov', '.m4v')):
                    files.append(full_path)
                    print(f"   🎬 Found: {item}")
        
        print(f"📊 Total videos found: {len(files)}")
        return sorted(files)
    except Exception as e:
        print(f"❌ Error getting playlist from {collection_path}: {e}")
        return []

def clear_screen():
    """Clear the screen and make it black"""
    try:
        # Multiple approaches to clear the screen on Pi
        commands = [
            # Clear framebuffer console
            ['sudo', 'sh', '-c', 'cat /dev/zero > /dev/fb0 2>/dev/null || true'],
            # Clear terminal
            ['clear'],
            # Turn off cursor blink
            ['sudo', 'sh', '-c', 'echo 0 > /sys/class/graphics/fbcon/cursor_blink 2>/dev/null || true']
        ]
        
        for cmd in commands:
            try:
                subprocess.run(cmd, timeout=2, check=False, 
                             stdout=subprocess.DEVNULL, 
                             stderr=subprocess.DEVNULL)
            except:
                continue  # Try next method
                
        print("🖥️ Screen cleared using available methods")
    except Exception as e:
        print(f"⚠️ Could not clear screen: {e}")

def set_playback_state(state):
    """Thread-safe playback state management"""
    global playback_state
    with playback_state_lock:
        old_state = playback_state
        playback_state = state
        print(f"🎮 Playback state: {old_state} → {state}")

def get_playback_state():
    """Get current playback state"""
    with playback_state_lock:
        return playback_state

def send_omxplayer_command(command):
    """Send command to OMXPlayer via DBUS"""
    global current_player_process
    
    if not current_player_process or current_player_process.poll() is not None:
        print("❌ No active OMXPlayer to send command to")
        return False
    
    try:
        # OMXPlayer DBUS commands
        dbus_cmd = [
            'dbus-send', 
            '--print-reply=literal', 
            '--session', 
            '--dest=org.mpris.MediaPlayer2.omxplayer',
            '/org/mpris/MediaPlayer2',
            f'org.mpris.MediaPlayer2.Player.{command}'
        ]
        
        result = subprocess.run(dbus_cmd, capture_output=True, timeout=2)
        if result.returncode == 0:
            print(f"✅ Sent OMXPlayer command: {command}")
            return True
        else:
            print(f"⚠️ OMXPlayer command failed: {command}")
            return False
            
    except Exception as e:
        print(f"❌ Error sending OMXPlayer command {command}: {e}")
        return False

def omxplayer_play(video_path):
    """Play video using omxplayer with pause/resume support"""
    global current_player_process, running, shutdown_event
    
    print(f"🎬 Playing with omxplayer: {os.path.basename(video_path)}")
    debug_thread_info()
    
    # CRITICAL: Ensure no other OMXPlayer is running
    cleanup_existing_omxplayers()
    
    # Set state to playing
    set_playback_state("playing")
    
    try:
        # omxplayer command with DBUS support for remote control
        cmd = [
            'omxplayer',
            '--no-osd',  # No on-screen display
            '--hw',  # Hardware acceleration
            '--refresh',  # Adjust refresh rate
            '--blank',  # Blank screen before starting
            video_path
        ]
        
        # Start omxplayer process
        current_player_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid  # Create new process group for easier cleanup
        )
        
        print(f"🎮 OMXPlayer started (PID: {current_player_process.pid})")
        debug_thread_info()
        
        # Wait for OMXPlayer to initialize DBUS interface
        time.sleep(1)
        
        # Playback monitoring loop with pause/resume support
        while running and not shutdown_event.is_set() and not force_stop_playback.is_set():
            # Check if process is still running (non-blocking)
            poll_result = current_player_process.poll()
            if poll_result is not None:
                # Process has finished
                print(f"🏁 Playback finished naturally (exit code: {poll_result})")
                set_playback_state("stopped")
                break
            
            # Handle pause state
            current_state = get_playback_state()
            if current_state == "paused":
                # Stay in pause monitoring loop
                time.sleep(0.5)
                continue
            elif current_state == "stopped":
                # Force stop requested
                break
            
            # Short sleep to allow interruption
            time.sleep(0.2)
        
        # Clean up process if still running
        if current_player_process and current_player_process.poll() is None:
            if force_stop_playback.is_set():
                print("🛑 Force stop requested")
            else:
                print("⏹️ Stopping omxplayer...")
            safe_terminate_omxplayer(current_player_process)
        
        current_player_process = None
        print("✅ OMXPlayer cleanup complete")
        debug_thread_info()
        
        # Check if we should stay stopped
        if force_stop_playback.is_set():
            set_playback_state("stopped")
            return "stopped"  # Signal to stop playlist
        
    except FileNotFoundError:
        print("❌ omxplayer not found - install with: sudo apt install omxplayer")
        set_playback_state("stopped")
        return False
    except Exception as e:
        print(f"❌ OMXPlayer error: {e}")
        set_playback_state("stopped")
        return False
    
    set_playback_state("stopped")
    return True

def cleanup_existing_omxplayers():
    """Kill any existing omxplayer processes to prevent conflicts"""
    try:
        # Find all omxplayer processes
        result = subprocess.run(['pgrep', 'omxplayer'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                if pid:
                    print(f"🔥 Killing existing OMXPlayer PID: {pid}")
                    try:
                        os.kill(int(pid), signal.SIGTERM)
                        time.sleep(0.5)
                        # Force kill if still running
                        try:
                            os.kill(int(pid), signal.SIGKILL)
                        except:
                            pass  # Already dead
                    except:
                        pass  # Process already gone
        
        # Brief pause to let cleanup finish
        time.sleep(0.5)
        
    except Exception as e:
        print(f"⚠️ Error cleaning up existing players: {e}")

def safe_terminate_omxplayer(process):
    """Safely terminate an OMXPlayer process"""
    if not process or process.poll() is not None:
        return  # Already dead
    
    try:
        # Try graceful termination first
        print("📤 Sending SIGTERM...")
        process.terminate()
        
        # Wait up to 2 seconds for graceful exit
        try:
            process.wait(timeout=2)
            print("✅ Process terminated gracefully")
            return
        except subprocess.TimeoutExpired:
            print("⏰ Graceful termination timed out")
        
        # Force kill if graceful didn't work
        print("💥 Force killing process...")
        process.kill()
        
        # Wait for force kill
        try:
            process.wait(timeout=1)
            print("✅ Process force killed")
        except subprocess.TimeoutExpired:
            print("⚠️ Force kill timed out - process may be zombie")
        
        # Kill entire process group if needed
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except:
            pass  # Process group already gone
            
    except Exception as e:
        print(f"⚠️ Error terminating process: {e}")
    
    # Final cleanup pause
    time.sleep(0.5)

def player_loop():
    """Main player loop using omxplayer"""
    global current_collection, current_collection_id, running
    global last_collection, last_collection_id, collection_changed
    
    print(f"🎵 Starting OMXPlayer loop")
    debug_thread_info()
    
    while running and not shutdown_event.is_set():
        playlist = []
        collection_for_playback = None
        
        # Check for collection changes
        with collection_lock:
            if (current_collection != last_collection or 
                current_collection_id != last_collection_id or 
                collection_changed):
                
                collection_for_playback = current_collection
                last_collection = current_collection
                last_collection_id = current_collection_id
                collection_changed = False
                
                print(f"📦 Collection changed to: {collection_for_playback}")
                playlist = get_playlist_files(collection_for_playback)
                print(f"📁 Found {len(playlist)} video files")
        
        if not playlist:
            print("😴 No playlist, sleeping...")
            time.sleep(5)
            continue
        
        # Play files in playlist
        for file_path in playlist:
            if not running or shutdown_event.is_set():
                return
            
            # Check if collection changed during playback
            with collection_lock:
                if collection_changed or current_collection != collection_for_playback:
                    print("🔄 Collection changed during playback")
                    break
            
            success = omxplayer_play(file_path)
            if not success:
                time.sleep(2)  # Brief pause on error
            
            # Brief pause between videos to prevent rapid starts
            if running and not shutdown_event.is_set():
                print("⏸️ Brief pause between videos...")
                time.sleep(2)  # Increased from 1 to 2 seconds

def cleanup():
    global running, current_player_process
    print("🧹 Cleaning up OMXPlayer resources...")
    running = False
    shutdown_event.set()
    force_stop_playback.set()  # Stop any ongoing playback
    
    debug_thread_info()
    
    # Stop current player if running
    if current_player_process and current_player_process.poll() is None:
        print("⏹️ Terminating current omxplayer...")
        safe_terminate_omxplayer(current_player_process)
        current_player_process = None
    
    # Clean up any remaining OMXPlayer processes
    cleanup_existing_omxplayers()
    
    # Clear screen on exit
    clear_screen()
    
    debug_thread_info()
    print("👋 Cleanup complete!")

def signal_handler(sig, frame):
    print(f"🛑 Received signal {sig}, cleaning up...")
    cleanup()
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
atexit.register(cleanup)

# Initialize collection - find where videos actually are
print("🔍 Initializing media collections...")
media_base_path, available_collections = get_collections()

if available_collections:
    if 'default' in available_collections:
        # Videos are directly in base directory
        current_collection = media_base_path
    else:
        # Videos are in subdirectories
        current_collection = os.path.join(media_base_path, available_collections[0])
    print(f"🎯 Initial collection: {current_collection}")
    print(f"📁 Available collections: {available_collections}")
    
    # Trigger initial collection change to start playing
    collection_changed = True
    current_collection_id = 1
    print("🚀 Marked initial collection for auto-start")
else:
    current_collection = "/media/internal"
    print(f"⚠️ No collections found, using fallback: {current_collection}")
    print("💡 Create test videos with:")
    print("   sudo mkdir -p /media/internal/test")
    print("   # Copy some .mp4 files to /media/internal/test/")

# Initialize playback state and events
paused_video_path = None
# Note: force_pause_playback and force_stop_playback are defined above as Event objects
# So we can safely clear them here
force_pause_playback.clear()  # Make sure pause flag starts clear
force_stop_playback.clear()   # Make sure stop flag starts clear
set_playback_state("playing")  # Start in playing state, not stopped
print(f"🎮 Initial playback state: {get_playback_state()}")
print(f"🚨 Events initialized - force_stop: {force_stop_playback.is_set()}, force_pause: {force_pause_playback.is_set()}")

# Start player thread
player_thread = Thread(target=player_loop, daemon=True, name="PlayerThread")
player_thread.start()
print("🎬 Player thread started")
debug_thread_info()

# Flask app
app = Flask(__name__)
CORS(app)

@app.route("/collections", methods=["GET"])
def list_collections():
    return jsonify(available_collections)

@app.route("/set_collection", methods=["POST"])
def set_collection():
    global current_collection, current_collection_id, collection_changed, current_player_process
    global force_stop_playback, force_pause_playback  # Add explicit global declarations

    collection = request.json.get("collection")
    if not collection:
        return jsonify({"status": "error", "message": "No collection specified"}), 400

    if collection not in available_collections:
        return jsonify({"status": "error", "message": "Invalid collection"}), 400

    if collection == 'default':
        new_path = media_base_path
    else:
        new_path = os.path.join(media_base_path, collection)
    
    print(f"🔄 Collection change request: {collection} -> {new_path}")
    
    with collection_lock:
        # Stop current playback with proper cleanup
        if current_player_process and current_player_process.poll() is None:
            print("⏹️ Stopping current playback for collection change")
            safe_terminate_omxplayer(current_player_process)
            current_player_process = None
        
        # Extra cleanup to prevent conflicts
        cleanup_existing_omxplayers()
        
        current_collection_id += 1
        current_collection = new_path
        collection_changed = True
        
        # Start playing new collection automatically
        force_stop_playback.clear()
        set_playback_state("playing")
        
    debug_thread_info()
    return jsonify({
        "status": "ok", 
        "collection": collection,
        "playback_state": get_playback_state()
    })

def clear_screen():
    """Clear the screen and make it black"""
    try:
        # Multiple approaches to clear the screen on Pi
        commands = [
            # Clear framebuffer console
            ['sudo', 'sh', '-c', 'cat /dev/zero > /dev/fb0 2>/dev/null || true'],
            # Clear terminal
            ['clear'],
            # Turn off cursor blink
            ['sudo', 'sh', '-c', 'echo 0 > /sys/class/graphics/fbcon/cursor_blink 2>/dev/null || true']
        ]
        
        for cmd in commands:
            try:
                subprocess.run(cmd, timeout=2, check=False, 
                             stdout=subprocess.DEVNULL, 
                             stderr=subprocess.DEVNULL)
            except:
                continue  # Try next method
                
        print("🖥️ Screen cleared using available methods")
    except Exception as e:
        print(f"⚠️ Could not clear screen: {e}")

@app.route("/play", methods=["POST"])
def play():
    """Start playing or resume paused playback"""
    global current_player_process, paused_video_path
    global force_pause_playback, force_stop_playback  # Add explicit global declarations
    current_state = get_playback_state()
    
    print(f"▶️ Play requested (current state: {current_state})")
    
    if current_state == "paused":
        # Clear pause flags and resume
        force_pause_playback.clear()
        
        if paused_video_path and os.path.exists(paused_video_path):
            print(f"🔄 Resuming video: {os.path.basename(paused_video_path)}")
            set_playback_state("playing")
            paused_video_path = None  # Clear paused state
            return jsonify({"status": "resumed", "state": "playing", "message": "Resuming paused video"})
        else:
            # No paused video, just start normal playback
            force_stop_playback.clear()
            set_playback_state("playing")
            return jsonify({"status": "started", "state": "playing"})
    
    elif current_state == "stopped":
        # Start playing from stopped state
        force_stop_playback.clear()
        force_pause_playback.clear()
        set_playback_state("playing") 
        return jsonify({"status": "started", "state": "playing"})
    
    elif current_state == "playing":
        return jsonify({"status": "already_playing", "state": "playing"})
    
    return jsonify({"status": "error", "message": "Unknown playback state"})

@app.route("/pause", methods=["POST"])
def pause():
    """Pause current video playback immediately"""
    global current_player_process, paused_video_path
    global force_pause_playback  # Add explicit global declaration
    current_state = get_playback_state()
    
    print(f"⏸️ IMMEDIATE Pause requested (current state: {current_state})")
    
    if current_state == "playing":
        if current_player_process and current_player_process.poll() is None:
            # Set immediate pause flag for fastest response
            force_pause_playback.set()
            
            # Set state to paused FIRST
            set_playback_state("paused")
            
            print("💾 Pausing playback (stopping process immediately)")
            
            # Force kill the process immediately - no graceful termination
            try:
                print(f"🔥 Force killing OMXPlayer PID: {current_player_process.pid}")
                current_player_process.kill()  # Immediate SIGKILL
                current_player_process.wait(timeout=1)  # Wait briefly for cleanup
            except Exception as e:
                print(f"⚠️ Error force killing: {e}")
            
            current_player_process = None
            
            return jsonify({
                "status": "paused", 
                "state": "paused", 
                "message": "Video paused immediately"
            })
        else:
            return jsonify({"status": "error", "message": "No video currently playing"})
    
    elif current_state == "paused":
        return jsonify({"status": "already_paused", "state": "paused"})
    
    else:
        return jsonify({"status": "error", "message": "Nothing to pause", "state": current_state})

@app.route("/stop", methods=["POST"])
def stop():
    """Stop playback completely and clear screen"""
    global current_player_process, paused_video_path
    global force_pause_playback, force_stop_playback  # Add explicit global declarations
    
    print("⏹️ Stop requested - will stop playlist and clear screen")
    
    # Set force stop flag to prevent new videos from starting
    force_stop_playback.set()
    force_pause_playback.clear()  # Clear any pause state
    set_playback_state("stopped")
    
    # Clear paused video tracking
    paused_video_path = None
    
    # Stop current player if running
    if current_player_process and current_player_process.poll() is None:
        print("🛑 Stopping current playback")
        safe_terminate_omxplayer(current_player_process)
        current_player_process = None
    
    # Extra cleanup to prevent conflicts
    cleanup_existing_omxplayers()
    
    # Clear the screen 
    clear_screen()
    
    return jsonify({
        "status": "stopped", 
        "state": "stopped", 
        "message": "Playback stopped and screen cleared"
    })

@app.route("/next", methods=["POST"])
def next_track():
    """Skip to next track (only works if currently playing)"""
    global current_player_process
    current_state = get_playback_state()
    
    print(f"⏭️ Next track requested (current state: {current_state})")
    
    if current_state in ["playing", "paused"]:
        if current_player_process and current_player_process.poll() is None:
            print("🛑 Stopping current track for next")
            safe_terminate_omxplayer(current_player_process)
            current_player_process = None
            
            # Don't set force_stop - let it continue to next video
            set_playback_state("playing")
            
            return jsonify({"status": "skipped", "state": "playing"})
        else:
            return jsonify({"status": "error", "message": "No track currently playing"})
    
    elif current_state == "stopped":
        return jsonify({"status": "error", "message": "Cannot skip when stopped. Use /play to start.", "state": "stopped"})
    
    return jsonify({"status": "error", "message": "Unknown state"})

@app.route("/status", methods=["GET"])
def get_status():
    """Get current system and playback status"""
    global paused_video_path  # Add global declaration
    
    thread_count = threading.active_count()
    is_omx_running = current_player_process is not None and current_player_process.poll() is None
    current_state = get_playback_state()
    
    status_info = {
        "status": "running",
        "thread_count": thread_count,
        "current_collection": os.path.basename(current_collection),
        "collection_id": current_collection_id,
        "playback_state": current_state,
        "omxplayer_running": is_omx_running,
        "force_stop_set": force_stop_playback.is_set()
    }
    
    # Add paused video info if relevant
    if current_state == "paused" and paused_video_path:
        status_info["paused_video"] = os.path.basename(paused_video_path)
        status_info["paused_video_exists"] = os.path.exists(paused_video_path)
    
    return jsonify(status_info)

@app.route("/debug", methods=["GET"])
def debug_status():
    """Debug endpoint to check current state"""
    global force_pause_playback, force_stop_playback, paused_video_path  # Add globals
    
    thread_count = threading.active_count()
    current_state = get_playback_state()
    
    debug_info = {
        "current_state": current_state,
        "force_stop_set": force_stop_playback.is_set(),
        "force_pause_set": force_pause_playback.is_set(),
        "running": running,
        "shutdown_event_set": shutdown_event.is_set(),
        "current_collection": current_collection,
        "available_collections": available_collections,
        "thread_count": thread_count,
        "omxplayer_running": current_player_process is not None and current_player_process.poll() is None
    }
    
    if paused_video_path:
        debug_info["paused_video"] = paused_video_path
        debug_info["paused_video_exists"] = os.path.exists(paused_video_path)
    
    return jsonify(debug_info)

@app.route("/emergency_cleanup", methods=["POST"])
def emergency_cleanup():
    """Emergency endpoint to kill all OMXPlayer processes"""
    global current_player_process  # Add global declaration
    
    print("🚨 Emergency cleanup requested")
    current_player_process = None
    cleanup_existing_omxplayers()
    
    return jsonify({"status": "cleaned_up", "message": "All OMXPlayer processes terminated"})

def run_flask_app():
    app.run(host="0.0.0.0", port=5000, threaded=True, use_reloader=False, debug=False)

# Start Flask
flask_thread = Thread(target=run_flask_app, daemon=True, name="FlaskThread")
flask_thread.start()
print("🌐 Flask started")
debug_thread_info()

# Main thread monitoring
print("💓 Main thread running with OMXPlayer backend...")
try:
    while running and not shutdown_event.is_set():
        time.sleep(10)
        thread_count = threading.active_count()
        print(f"💓 Heartbeat - Threads: {thread_count}")
        if thread_count > 5:
            print("⚠️ High thread count detected:")
            debug_thread_info()
except KeyboardInterrupt:
    print("🛑 Keyboard interrupt")
    cleanup()

print("🏁 Main thread exiting")
debug_thread_info()
# mp4museum v6.9 forked by dballsworth - june 2024 - CPU OPTIMIZED
# (c) julius schmiedel - http://mp4museum.org4
import sys
import os
import subprocess
import time
import vlc
import glob
import signal
import atexit
from threading import Thread, Event, Lock

player = None  # ensure player is initialized
vlc_instance = None  # Global VLC instance to reuse
running = True  # Global flag to control loops
playback_finished = Event()  # Event-driven playback control

# Flask API for collection control
from flask import Flask, jsonify, request
collection_lock = Lock()
shutdown_event = Event()  # Event to signal threads to exit

# Cache for collections to avoid repeated file system operations
collections_cache = {}
collections_cache_time = 0
CACHE_DURATION = 30  # Cache collections for 30 seconds

# GPIO REMOVED - not needed for this setup
print("🚀 GPIO support disabled - using API/web control only")

# read audio device config
audiodevice = "0"

# global variable for current collection
current_collection = "/media/"  # Keep this as is for now
current_collection_id = 0
collection_ready = False

# Add global variables for collection switching
last_collection = None
last_collection_id = -1
collection_changed = False  # New flag for cleaner change detection

# Global startup mode flag
startup_mode = True

if os.path.isfile('/boot/alsa.txt'):
    f = open('/boot/alsa.txt', 'r')
    audiodevice = f.read(1)

# OPTIMIZATION: Create single VLC instance to reuse
def initialize_vlc():
    global vlc_instance, player
    vlc_instance = vlc.Instance('-q -A alsa --alsa-audio-device hw:' + audiodevice)
    player = vlc_instance.media_player_new()
    
    # Set up event handling for playback completion
    event_manager = player.event_manager()
    event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, on_media_end)

def on_media_end(event):
    """Event callback when media playback ends - eliminates polling loop"""
    global playback_finished
    playback_finished.set()

# OPTIMIZATION: Cached collection retrieval
def get_collections_cached():
    global collections_cache, collections_cache_time
    current_time = time.time()
    
    if current_time - collections_cache_time > CACHE_DURATION:
        collections_cache = sorted([d for d in glob.glob("/media/internal/*") if os.path.isdir(d)])
        collections_cache_time = current_time
    
    return collections_cache

# STEP 2: Add this initialization AFTER the GPIO setup (around line 40, after the GPIO.setup lines):
# Initialize collection properly after everything else is set up
def initialize_collection():
    global current_collection
    all_collections = get_collections_cached()
    if all_collections:
        current_collection = all_collections[0]  # Start with first available collection
        print(f"🎯 Initial collection set to: {current_collection}")
    else:
        current_collection = "/media/internal"  # Fallback if no collections found
        print(f"🎯 No collections found, using fallback: {current_collection}")
    sys.stdout.flush()

# Initialize VLC and collection
initialize_vlc()
initialize_collection()

# GPIO functions removed - control via API only

# OPTIMIZATION: Event-driven playback instead of polling
def vlc_play(source, collection):
    global player, running, playback_finished, vlc_instance
    
    print(f"🧪 DEBUG: Current collection at playback time: {collection}")
    if not source.startswith(collection):
        print(f"⚠️ WARNING: File {source} is outside the expected collection path {collection}")
        return  # Skip playback if the file is not in the correct collection
    else:
        print(f"🎬 Now playing from collection: {collection}")
        print(f"🎬 File: {source}")
    sys.stdout.flush()
    
    # OPTIMIZATION: Reuse existing VLC instance, just change media
    if "loop." in source:
        # For loop files, we need a new instance with repeat
        loop_instance = vlc.Instance('--input-repeat=999999999 -q -A alsa --alsa-audio-device hw:' + audiodevice)
        loop_player = loop_instance.media_player_new()
        media = loop_instance.media_new(source)
        loop_player.set_media(media)
        loop_player.play()
        
        # Use simpler blocking wait for loop files
        time.sleep(1)
        while loop_player.get_state() in (3, 4) and running:
            time.sleep(0.5)  # Longer sleep for loop files
            if shutdown_event.is_set():
                break
        
        media.release()
        loop_player.release()
        loop_instance.release()
    else:
        # OPTIMIZATION: Reuse global player instance
        media = vlc_instance.media_new(source)
        player.set_media(media)
        playback_finished.clear()  # Reset the event
        player.play()
        
        time.sleep(0.1)  # Brief pause to let playback start
        
        # OPTIMIZATION: Event-driven waiting instead of polling
        while running and not shutdown_event.is_set():
            # Wait for either playback to finish or shutdown signal
            if playback_finished.wait(timeout=0.5):  # Check every 500ms instead of 100ms
                break
            
            # Only check player state occasionally as fallback
            state = player.get_state()
            if state not in (3, 4):  # Not playing or paused
                break
        
        media.release()

# find a file, and if found, return its path (for sync)
def search_file(file_name):
    # Use glob to find files matching the pattern in both directories
    file_path_media = f'/media/*/{file_name}'
    file_path_boot = f'/boot/{file_name}'
    
    matching_files = glob.glob(file_path_media) + glob.glob(file_path_boot)

    if matching_files:
        # Return the first found file name
        return matching_files[0]

    # Return False if the file is not found
    return False

# *** run player ****

# Initial startup video (optional; disable if not needed)
boot_video = "/home/pi/mp4museum-boot.mp4"
if os.path.exists(boot_video):
    vlc_play(boot_video, os.path.dirname(boot_video))

# GPIO event detection removed - API control only

# check for sync mode instructions
enableSync = search_file("sync-leader.txt")
syncFile = search_file("sync.mp4")
if syncFile and enableSync:
    print("Sync Mode LEADER:" + syncFile)
    subprocess.run(["omxplayer-sync", "-u", "-m", syncFile]) 

enableSync = search_file("sync-player.txt")
syncFile = search_file("sync.mp4")
if syncFile and enableSync:
    print("Sync Mode PLAYER:" + syncFile)
    subprocess.run(["omxplayer-sync", "-u", "-l",  syncFile]) 

# OPTIMIZATION: Simplified playback loop
def start_player_loop():
    global current_collection, current_collection_id, startup_mode
    global last_collection, last_collection_id, collection_changed, collection_ready
    global running
    
    all_collections = get_collections_cached()
    print(f"🎵 Available collections: {all_collections}")
    print(f"📡 Starting player loop with collection: {current_collection}")
    sys.stdout.flush()

    if startup_mode:
        startup_mode = False  # Move this up to prevent accidental re-entry
        print(f"🚀 Startup mode: playing only from {current_collection}")
        sys.stdout.flush()
        playlist = sorted(glob.glob(os.path.join(current_collection, "*.*")))
        for file in playlist:
            if not running or shutdown_event.is_set():
                return
            vlc_play(file, current_collection)  

    while running and not shutdown_event.is_set():
        collection_for_playback = None
        playlist = []
        collection_id_snapshot = current_collection_id

        # OPTIMIZATION: Reduced lock contention
        collection_changed_local = False
        with collection_lock:
            if (current_collection != last_collection or 
                current_collection_id != last_collection_id or 
                collection_changed):
                
                collection_for_playback = current_collection
                print(f"📦 DEBUG: Locked-in collection_for_playback: {collection_for_playback}")
                sys.stdout.flush()
                
                # OPTIMIZATION: Cache playlist instead of recalculating
                playlist = sorted([
                    file for file in glob.glob(os.path.join(collection_for_playback, "*.*"))
                    if os.path.isfile(file)
                ])
                
                print(f"🔄 Collection change detected!")
                print(f"🧪 Playlist for {collection_for_playback}: {[os.path.basename(f) for f in playlist]}")
                sys.stdout.flush()

                last_collection = collection_for_playbook = collection_for_playback
                last_collection_id = collection_id_snapshot
                collection_changed = False
                collection_changed_local = True

        if not playlist or not collection_for_playback:
            time.sleep(2)  # OPTIMIZATION: Longer sleep when idle
            continue

        for file in playlist:
            if not running or shutdown_event.is_set():
                return
                
            # OPTIMIZATION: Less frequent collection change checking
            if collection_changed_local:
                with collection_lock:
                    if (current_collection != collection_for_playback or
                        current_collection_id != collection_id_snapshot or
                        collection_changed):
                        print("🔁 Collection changed mid-playback. Breaking loop.")
                        sys.stdout.flush()
                        break

            print(f"🎬 Playing: {os.path.basename(file)} from {collection_for_playback}")
            sys.stdout.flush()

            vlc_play(file, collection_for_playback)

        if not playlist:
            print(f"⚠️ No playable files found in collection: {collection_for_playback}")
            sys.stdout.flush()
            time.sleep(10)  # OPTIMIZATION: Longer sleep when no files found
            continue

# Define cleanup function
def cleanup():
    global running, player, vlc_instance
    print("🧹 Cleaning up resources...")
    running = False
    shutdown_event.set()
    
    # Stop player if it exists
    if player:
        try:
            player.stop()
            player.release()
        except Exception as e:
            print(f"Error stopping player during cleanup: {e}")
    
    # Release VLC instance
    if vlc_instance:
        try:
            vlc_instance.release()
        except Exception as e:
            print(f"Error releasing VLC instance: {e}")
    
    # GPIO cleanup removed - not using GPIO
    print("✅ Cleanup completed")
    
    print("👋 Goodbye!")
    sys.stdout.flush()

# Signal handler for graceful shutdown
def signal_handler(sig, frame):
    print("🛑 Received shutdown signal, cleaning up...")
    cleanup()
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
signal.signal(signal.SIGTERM, signal_handler)  # Termination signal
atexit.register(cleanup)  # Register cleanup on normal exit

# start player loop in a separate thread
player_thread = Thread(target=start_player_loop, daemon=True)
player_thread.start()

# Flask app and API endpoints
from flask_cors import CORS
app = Flask(__name__)
CORS(app)

@app.route("/collections", methods=["GET"])
def list_collections():
    # OPTIMIZATION: Use cached collections
    folders = [os.path.basename(d) for d in get_collections_cached()]
    return jsonify(folders)

@app.route("/set_collection", methods=["POST"])
def set_collection():
    global current_collection
    global current_collection_id
    global startup_mode
    global player
    global collection_changed
    global collection_ready

    collection = request.json.get("collection")
    all_collections = [os.path.basename(d) for d in get_collections_cached()]
    
    if collection not in all_collections:
        return jsonify({"status": "error", "message": "Invalid collection"}), 400

    path = f"/media/videos/{collection}"
    if not os.path.exists(path):
        return jsonify({"status": "error", "message": "Collection path does not exist"}), 400

    print(f"🧪 Received collection switch request to: {collection}")
    print(f"🧪 Full path resolved: {path}")
    sys.stdout.flush()

    startup_mode = False

    with collection_lock:
        try:
            if player is not None:
                player.stop()
                playback_finished.set()  # Signal immediate stop
                print("🛑 Forcefully stopped current player")
        except Exception as e:
            print(f"⚠️ Error stopping player: {e}")

        current_collection_id += 1
        current_collection = path
        collection_ready = True
        collection_changed = True
        print(f"🧪 Post-update check — current_collection: {current_collection}")
        sys.stdout.flush()

    return jsonify({"status": "ok", "collection": collection})

@app.route("/next", methods=["POST"])
def next_track():
    """Skip to next track"""
    if player:
        player.stop()
        playback_finished.set()
        return jsonify({"status": "skipped"})
    return jsonify({"status": "error", "message": "No player available"})

@app.route("/play", methods=["POST"])
def play():
    if player:
        player.play()
        return jsonify({"status": "playing"})
    return jsonify({"status": "error", "message": "No player available"})

@app.route("/pause", methods=["POST"])
def pause():
    if player:
        player.pause()
        return jsonify({"status": "paused"})
    return jsonify({"status": "error", "message": "No player available"})

@app.route("/restart", methods=["POST"])
def restart():
    print("♻️ Restarting server via subprocess...")
    sys.stdout.flush()
    subprocess.Popen(["python3"] + sys.argv)
    os._exit(0)

# OPTIMIZATION: Run Flask with optimized settings
def run_flask_app():
    app.run(host="0.0.0.0", port=5000, threaded=True, use_reloader=False, 
            processes=1, debug=False)  # Disable debug mode for production

flask_thread = Thread(target=run_flask_app, daemon=True)
flask_thread.start()

# OPTIMIZATION: Longer sleep in main thread
try:
    while running and not shutdown_event.is_set():
        time.sleep(5)  # Increased from 1 second
except KeyboardInterrupt:
    print("🛑 Keyboard interrupt received in main thread")
    cleanup()

print("🏁 Main thread exiting")
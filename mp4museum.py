# mp4museum v6.3 forked by dballsworth - june 2024
# (c) julius schmiedel - http://mp4museum.org4
import sys
import os

player = None  # ensure player is initialized

# Flask API for collection control
from flask import Flask, jsonify, request
from threading import Thread
from threading import Lock
collection_lock = Lock()

try:
    import RPi.GPIO as GPIO
    print("✅ Using real RPi.GPIO")
except (ImportError, RuntimeError, ModuleNotFoundError):
    try:
        from fake_rpi import GPIO
        print("🧪 Using fake_rpi.GPIO for non-Pi development.")
    except ImportError:
        raise ImportError("⚠️ Neither RPi.GPIO nor fake_rpi.GPIO could be loaded.")

import time, vlc, os, glob
import subprocess

 # read audio device config
audiodevice = "0"

# global variable for current collection
current_collection = "/media/"  # Keep this as is for now
current_collection_id = 0
collection_ready = False

# STEP 2: Add this initialization AFTER the GPIO setup (around line 40, after the GPIO.setup lines):
# Initialize collection properly after everything else is set up
def initialize_collection():
    global current_collection
    all_collections = sorted([d for d in glob.glob("/media/videos/*") if os.path.isdir(d)])
    if all_collections:
        current_collection = all_collections[0]  # Start with first available collection
        print(f"🎯 Initial collection set to: {current_collection}")
    else:
        current_collection = "/media/videos"  # Fallback if no collections found
        print(f"🎯 No collections found, using fallback: {current_collection}")
    sys.stdout.flush()

# Call the initialization
initialize_collection()

# Add global variables for collection switching
last_collection = None
last_collection_id = -1
collection_changed = False  # New flag for cleaner change detection

# Global startup mode flag
startup_mode = True

if os.path.isfile('/boot/alsa.txt'):
    f = open('/boot/alsa.txt', 'r')
    audiodevice = f.read(1)

# setup GPIO pin
GPIO.setmode(GPIO.BOARD)
GPIO.setup(11, GPIO.IN, pull_up_down = GPIO.PUD_DOWN)
GPIO.setup(13, GPIO.IN, pull_up_down = GPIO.PUD_DOWN)

# functions to be called by event listener
# with code to filter interference / static discharges
def buttonPause(channel):
    inputfilter = 0
    for x in range(0,200):
        if GPIO.input(11):
            inputfilter = inputfilter + 1
        time.sleep(.001)
    if (inputfilter > 50):
        player.pause()

def buttonNext(channel):
    inputfilter = 0
    for x in range(0,200):
        if GPIO.input(13):
            inputfilter = inputfilter + 1
        time.sleep(.001)
    if (inputfilter > 50):
        player.stop()

# play media with vlc
# Replace your existing vlc_play function with this version:

# Replace your vlc_play function with this corrected version:

# First, revert vlc_play to the original (but keep it simple):
def vlc_play(source, collection):
    print(f"🧪 DEBUG: Current collection at playback time: {collection}")
    if not source.startswith(collection):
        print(f"⚠️ WARNING: File {source} is outside the expected collection path {collection}")
        return  # Skip playback if the file is not in the correct collection
    else:
        print(f"🎬 Now playing from collection: {collection}")
        print(f"🎬 File: {source}")
    sys.stdout.flush()
    
    if("loop." in source):
        vlc_instance = vlc.Instance('--input-repeat=999999999 -q -A alsa --alsa-audio-device hw:' + audiodevice)
    else:
        vlc_instance = vlc.Instance('-q -A alsa --alsa-audio-device hw:'+ audiodevice)
    
    global player
    player = vlc_instance.media_player_new()
    media = vlc_instance.media_new(source)
    player.set_media(media)
    player.play()
    time.sleep(1)
    
    current_state = player.get_state()
    while current_state == 3 or current_state == 4:
        time.sleep(.01)
        current_state = player.get_state()
    
    media.release()
    player.release()


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

# add event listener which reacts to GPIO signal
GPIO.add_event_detect(11, GPIO.RISING, callback = buttonPause, bouncetime = 234)
GPIO.add_event_detect(13, GPIO.RISING, callback = buttonNext, bouncetime = 1234)

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


# playback loop in a function
def start_player_loop():
    global current_collection
    global current_collection_id
    global startup_mode
    global last_collection
    global last_collection_id
    global collection_changed
    global collection_ready
    
    all_collections = sorted([d for d in glob.glob("/media/videos/*") if os.path.isdir(d)])
    print(f"🎵 Available collections: {all_collections}")
    print(f"📡 Starting player loop with collection: {current_collection}")
    sys.stdout.flush()

    if startup_mode:
        startup_mode = False  # Move this up to prevent accidental re-entry
        print(f"🚀 Startup mode: playing only from {current_collection}")
        sys.stdout.flush()
        playlist = sorted(glob.glob(os.path.join(current_collection, "*.*")))
        for file in playlist:
            vlc_play(file, current_collection)  

    while True:
        collection_for_playback = None
        playlist = []
        collection_id_snapshot = current_collection_id

        with collection_lock:
            if (current_collection != last_collection or 
                current_collection_id != last_collection_id or 
                collection_changed):
                
                collection_for_playback = current_collection
                print(f"📦 DEBUG: Locked-in collection_for_playback: {collection_for_playback}")
                sys.stdout.flush()
                playlist = sorted([
                    file for file in glob.glob(os.path.join(collection_for_playback, "*.*"))
                    if os.path.isfile(file)
                ])
                
                print(f"🔄 Collection change detected!")
                print(f"🧪 Playlist for {collection_for_playback}: {[os.path.basename(f) for f in playlist]}")
                sys.stdout.flush()

                last_collection = collection_for_playback
                last_collection_id = collection_id_snapshot
                collection_changed = False  # Reset the flag here

        if not playlist or not collection_for_playback:
            time.sleep(1)
            continue

        for file in playlist:
            with collection_lock:
                if (current_collection != collection_for_playback or
                    current_collection_id != collection_id_snapshot or
                    collection_changed):
                    print("🔁 Collection changed mid-playback. Breaking loop.")
                    sys.stdout.flush()
                    break  # Exit the current playlist loop if the collection has changed

            print(f"🎬 Playing: {os.path.basename(file)} from {collection_for_playback}")
            sys.stdout.flush()

            vlc_play(file, collection_for_playback)

            with collection_lock:
                if (current_collection != collection_for_playback or
                    current_collection_id != collection_id_snapshot or
                    collection_changed):
                    print("🔁 Collection changed mid-playback. Breaking loop.")
                    sys.stdout.flush()
                    break

        if not playlist:
            print(f"⚠️ No playable files found in collection: {collection_for_playback}")
            sys.stdout.flush()
            continue


# start player loop in a separate thread
player_thread = Thread(target=start_player_loop, daemon=True)
player_thread.start()

# Flask app and API endpoints
app = Flask(__name__)

@app.route("/collections", methods=["GET"])
def list_collections():
    folders = [os.path.basename(d) for d in glob.glob("/media/videos/*") if os.path.isdir(d)]
    return jsonify(folders)

# And fix the /set_collection endpoint to force immediate collection switch:
@app.route("/set_collection", methods=["POST"])
def set_collection():
    global current_collection
    global current_collection_id
    global startup_mode
    global player
    global collection_changed
    global collection_ready

    collection = request.json.get("collection")
    all_collections = [os.path.basename(d) for d in glob.glob("/media/videos/*") if os.path.isdir(d)]
    
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
                player.release()  # Release the player to free resources
                print("🛑 Forcefully stopped and released current player")
        except Exception as e:
            print(f"⚠️ Error stopping player: {e}")

        current_collection_id += 1
        current_collection = path
        collection_ready = True
        collection_changed = True
        print(f"🧪 Post-update check — current_collection: {current_collection}")
        sys.stdout.flush()

    return jsonify({"status": "ok", "collection": collection})

@app.route("/play", methods=["POST"])
def play():
    player.play()
    return jsonify({"status": "playing"})

@app.route("/pause", methods=["POST"])
def pause():
    player.pause()
    return jsonify({"status": "paused"})

@app.route("/restart", methods=["POST"])
def restart():
    os.execv(sys.executable, ['python3'] + sys.argv)

app.run(host="0.0.0.0", port=5000)
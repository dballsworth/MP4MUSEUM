# mp4museum v6.3 forked by dballsworth - june 2024
# (c) julius schmiedel - http://mp4museum.org4
import sys
import os

player = None  # ensure player is initialized

# Flask API for collection control
from flask import Flask, jsonify, request
from threading import Thread

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
    
    all_collections = sorted([d for d in glob.glob("/media/videos/*") if os.path.isdir(d)])
    print(f"🎵 Available collections: {all_collections}")
    print(f"📡 Starting player loop with collection: {current_collection}")
    sys.stdout.flush()

    if startup_mode:
        for collection in all_collections:
            playlist = sorted(glob.glob(os.path.join(collection, "*.*")))
            for file in playlist:
                vlc_play(file, collection)
        startup_mode = False

    playlist = []
    
    while True:
        print(f"🔄 Loop check - Current: {current_collection}")
        print(f"🔄 Last: {last_collection}, Changed: {collection_changed}")
        sys.stdout.flush()
        
        # Check if collection changed
        if (current_collection != last_collection or 
            current_collection_id != last_collection_id or 
            collection_changed):
            
            print(f"🔄 Collection change detected! Building playlist for: {current_collection}")
            sys.stdout.flush()
            
            playlist = sorted([
                file for file in glob.glob(os.path.join(current_collection, "*.*"))
                if os.path.isfile(file)
            ])
            
            print(f"🎵 Found {len(playlist)} files: {[os.path.basename(f) for f in playlist]}")
            
            # Update tracking variables
            last_collection = current_collection
            last_collection_id = current_collection_id
            collection_changed = False
            
            if not playlist:
                print(f"⚠️ No playable media found in: {current_collection}")
            sys.stdout.flush()

        if playlist:
            for file in playlist:
                print(f"🎬 Playing: {os.path.basename(file)} from {current_collection}")
                sys.stdout.flush()
                
                # Check if collection changed during playback
                if (current_collection != last_collection or 
                    current_collection_id != last_collection_id or 
                    collection_changed):
                    print("🔁 Collection changed mid-playback. Breaking loop.")
                    sys.stdout.flush()
                    break
                vlc_play(file, current_collection)
        else:
            print(f"💤 No playlist, waiting... Current collection: {current_collection}")
            sys.stdout.flush()
            time.sleep(1)

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
    
    collection = request.json.get("collection")
    path = f"/media/videos/{collection}"
    print(f"🧪 Received collection switch request to: {collection}")
    print(f"🧪 Full path resolved: {path}")
    print(f"🧪 Path exists? {os.path.isdir(path)}")
    sys.stdout.flush()
    
    if os.path.isdir(path):
        startup_mode = False
        
        # FORCE stop current playback immediately
        try:
            if player is not None:
                player.stop()
                print("🛑 Forcefully stopped current player")
                sys.stdout.flush()
        except Exception as e:
            print(f"⚠️ Error stopping player: {e}")
        
        # Update collection variables
        current_collection = path
        current_collection_id += 1
        collection_changed = True
        
        print(f"🎯 Collection set to: {current_collection}")
        print(f"🎯 Collection ID: {current_collection_id}")
        sys.stdout.flush()
        
        return jsonify({"status": "ok", "collection": collection})
    
    return jsonify({"status": "error", "message": "Invalid collection"}), 400
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
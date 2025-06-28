def clear_screen():
    """Clear the screen and make it black - improved version"""
    try:
        print("🖥️ Clearing screen...")
        
        # Multiple approaches to clear the screen on Pi
        commands = [
            # Kill any OMXPlayer first (they control the framebuffer)
            ['sudo', 'pkill', '-f', 'omxplayer'],
            # Clear framebuffer console
            ['sudo', 'sh', '-c', 'cat /dev/zero > /dev/fb0 2>/dev/null || true'],
            # Reset console
            ['reset'],
            # Clear terminal
            ['clear'],
            # Turn off cursor blink
            ['sudo', 'sh', '-c', 'echo 0 > /sys/class/graphics/fbcon/cursor_blink 2>/dev/null || true'],
            # Restore console to text mode
            ['sudo', 'chvt', '1'],
            # Final clear
            ['clear']
        ]
        
        for i, cmd in enumerate(commands):
            try:
                print(f"   Step {i+1}: {' '.join(cmd[:3])}...")
                result = subprocess.run(cmd, timeout=3, check=False, 
                                     capture_output=True)
                if result.returncode == 0:
                    print(f"   ✅ Step {i+1} succeeded")
                else:
                    print(f"   ⚠️ Step {i+1} returned {result.returncode}")
                time.sleep(0.2)  # Brief pause between commands
            except subprocess.TimeoutExpired:
                print(f"   ⏰ Step {i+1} timed out")
            except Exception as e:
                print(f"   ❌ Step {i+1} error: {e}")
                
        print("🖥️ Screen clearing complete")
        
    except Exception as e:
        print(f"⚠️ Could not clear screen: {e}")

def cleanup():
    global running, current_player_process
    print("🧹 Starting cleanup...")
    running = False
    shutdown_event.set()
    force_stop_playback.set()
    
    debug_thread_info()
    
    # Stop current player if running
    if current_player_process and current_player_process.poll() is None:
        print("⏹️ Terminating current omxplayer...")
        safe_terminate_omxplayer(current_player_process)
        current_player_process = None
    
    # Clean up any remaining OMXPlayer processes
    print("🔥 Cleaning up all OMXPlayer processes...")
    cleanup_existing_omxplayers()
    
    # Wait a moment for processes to fully terminate
    print("⏳ Waiting for processes to terminate...")
    time.sleep(1)
    
    # Clear screen AFTER all video processes are dead
    print("🖥️ Clearing screen...")
    clear_screen()
    
    # Give screen clearing more time to complete
    print("⏳ Allowing screen clear to complete...")
    time.sleep(2)
    
    debug_thread_info()
    print("👋 Cleanup complete!")

def signal_handler(sig, frame):
    print(f"\n🛑 Received signal {sig}, cleaning up...")
    
    # Do cleanup
    cleanup()
    
    # Additional screen restoration attempts
    print("🔄 Final screen restoration...")
    try:
        # Force console back to text mode
        subprocess.run(['sudo', 'chvt', '1'], timeout=2, check=False)
        time.sleep(0.5)
        
        # Reset terminal completely
        subprocess.run(['reset'], timeout=2, check=False)
        time.sleep(0.5)
        
        # Final clear
        subprocess.run(['clear'], timeout=1, check=False)
        
        # Show cursor
        print("\033[?25h", end='', flush=True)  # ANSI show cursor
        
    except Exception as e:
        print(f"⚠️ Final restoration error: {e}")
    
    print("\n🏁 Exiting cleanly...")
    
    # Allow time for all output to flush
    sys.stdout.flush()
    sys.stderr.flush()
    time.sleep(1)
    
    # Now exit
    sys.exit(0)

def cleanup_existing_omxplayers():
    """Kill any existing omxplayer processes to prevent conflicts - improved version"""
    try:
        print("🔍 Looking for existing OMXPlayer processes...")
        
        # Find all omxplayer processes
        result = subprocess.run(['pgrep', '-f', 'omxplayer'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            pids = [pid.strip() for pid in result.stdout.strip().split('\n') if pid.strip()]
            print(f"🔥 Found {len(pids)} OMXPlayer processes to kill")
            
            for pid in pids:
                if pid:
                    print(f"   Killing PID: {pid}")
                    try:
                        # Try graceful first
                        os.kill(int(pid), signal.SIGTERM)
                        time.sleep(0.3)
                        
                        # Check if still running, force kill if needed
                        try:
                            os.kill(int(pid), 0)  # Test if process exists
                            print(f"   Force killing PID: {pid}")
                            os.kill(int(pid), signal.SIGKILL)
                        except ProcessLookupError:
                            print(f"   ✅ PID {pid} terminated gracefully")
                            
                    except ProcessLookupError:
                        print(f"   ✅ PID {pid} already gone")
                    except Exception as e:
                        print(f"   ⚠️ Error killing PID {pid}: {e}")
        else:
            print("✅ No existing OMXPlayer processes found")
        
        # Extra safety - use pkill as backup
        print("🔄 Using pkill as backup...")
        subprocess.run(['sudo', 'pkill', '-9', '-f', 'omxplayer'], 
                      timeout=3, check=False, capture_output=True)
        
        # Brief pause to let cleanup finish
        time.sleep(1)
        
        print("✅ OMXPlayer cleanup complete")
        
    except Exception as e:
        print(f"⚠️ Error cleaning up existing players: {e}")
        # Try nuclear option
        try:
            subprocess.run(['sudo', 'pkill', '-9', '-f', 'omxplayer'], 
                          timeout=2, check=False, capture_output=True)
        except:
            pass
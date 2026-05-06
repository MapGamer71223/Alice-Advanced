import os
import platform
import random
import subprocess
import sys
import time
import webbrowser
from datetime import datetime

import psutil
import pyjokes

# Optional automation libraries (Windows)
try:
    import pyautogui
except Exception:
    pyautogui = None

try:
    import pygetwindow as gw
except Exception:
    gw = None

try:
    import keyboard
except Exception:
    keyboard = None

# For volume control on Windows (optional, fallback available)
try:
    from ctypes import POINTER, cast
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
except Exception:
    AudioUtilities = None
    IAudioEndpointVolume = None

# keep your existing actions and helpers
def open_google():
    webbrowser.open("https://www.google.com")

def open_gmail():
    webbrowser.open("https://mail.google.com")

def open_youtube():
    webbrowser.open("https://www.youtube.com")

def search_youtube(query):
    webbrowser.open(f"https://www.youtube.com/results?search_query={query}")

def search_google(query):
    webbrowser.open(f"https://www.google.com/search?q={query}")

def tell_time():
    now = datetime.now()
    return f"The current time is {now.strftime('%I:%M %p')}"

def tell_date():
    now = datetime.now()
    return f"Today's date is {now.strftime('%A, %B %d, %Y')}"

def open_app(app_name):
    try:
        # Platform-specific launching
        if platform.system() == "Windows":
            if app_name == "notepad":
                subprocess.Popen(['notepad'])
            elif app_name == "calculator":
                subprocess.Popen(['calc'])
            elif app_name == "explorer":
                subprocess.Popen(['explorer'])
            else:
                # attempt to open common program by name or path
                try:
                    os.startfile(app_name)
                except Exception:
                    subprocess.Popen([app_name])
        elif platform.system() == "Darwin":  # macOS
            subprocess.Popen(['open', '-a', app_name])
        elif platform.system() == "Linux":
            subprocess.Popen([app_name])
        return f"Opening {app_name.capitalize()}..."
    except Exception as e:
        return f"Sorry, I couldn’t find or open {app_name}. ({e})"

def tell_joke():
    return pyjokes.get_joke()

def get_system_info():
    cpu = psutil.cpu_percent()
    mem = psutil.virtual_memory().percent
    bat = "N/A"
    try:
        battery = psutil.sensors_battery()
        if battery:
            bat = battery.percent
    except Exception:
        pass
    return f"CPU: {cpu}%, RAM: {mem}%, Battery: {bat}%"

def tell_weather(city=None):
    # Placeholder - add your weather API or external module!
    if city:
        return f"Weather info for {city}: Sunny, 28°C (mockup)"
    return "You need to specify a city for weather info!"

def set_reminder(text):
    # For a real system: write to a DB/scheduler, notify at time
    return f"Reminder set: {text}"

def play_music(song=None):
    if song:
        webbrowser.open(f"https://www.youtube.com/results?search_query={song}")
        return f"Playing music: {song}"
    else:
        webbrowser.open("https://www.youtube.com")
        return "Opened YouTube. What song would you like?"

def search_web(query):
    webbrowser.open(f"https://www.google.com/search?q={query}")
    return f"Searching Google for '{query}'..."

def get_suggestion():
    suggestions = [
        "You can ask me to open any website or app.",
        "Try saying 'Tell me a joke' or 'What's the weather in Paris?'",
        "Want system info? Say 'Show my PC stats'.",
        "Ask 'Play music' or name your favorite song.",
        "Set a reminder by saying 'Remind me to ...'",
    ]
    return random.choice(suggestions)

#
# ---- Windows / automation helpers ----
#
def is_windows():
    return platform.system() == "Windows"

def list_windows():
    if not gw:
        return "Window management library not installed."
    wins = gw.getAllTitles()
    wins = [w for w in wins if w and w.strip()]
    return "\n".join(wins[:30]) or "No windows detected."

def switch_to_window(title_fragment):
    if not gw:
        return "Window management not available."
    try:
        candidates = [w for w in gw.getAllTitles() if title_fragment.lower() in (w or "").lower()]
        if not candidates:
            return f"No window with '{title_fragment}' found."
        win = gw.getWindowsWithTitle(candidates[0])[0]
        win.activate()
        return f"Switched to window: {candidates[0]}"
    except Exception as e:
        return f"Could not switch window: {e}"

def close_window(title_fragment=None):
    try:
        if not gw:
            return "Window management not available."
        if title_fragment:
            candidates = [w for w in gw.getAllTitles() if title_fragment.lower() in (w or "").lower()]
            if not candidates:
                return f"No window with '{title_fragment}' found to close."
            wobj = gw.getWindowsWithTitle(candidates[0])[0]
            wobj.close()
            return f"Closed window: {candidates[0]}"
        else:
            # close active
            active = gw.getActiveWindow()
            if active:
                title = active.title
                active.close()
                return f"Closed active window: {title}"
            return "No active window to close."
    except Exception as e:
        return f"Could not close window: {e}"

def minimize_window(title_fragment=None):
    if not gw:
        return "Window management not available."
    try:
        if title_fragment:
            candidates = [w for w in gw.getAllTitles() if title_fragment.lower() in (w or "").lower()]
            if not candidates:
                return f"No window with '{title_fragment}' found to minimize."
            win = gw.getWindowsWithTitle(candidates[0])[0]
            win.minimize()
            return f"Minimized {candidates[0]}"
        else:
            active = gw.getActiveWindow()
            if active:
                active.minimize()
                return f"Minimized {active.title}"
            return "No active window to minimize."
    except Exception as e:
        return f"Could not minimize window: {e}"

def maximize_window(title_fragment=None):
    if not gw:
        return "Window management not available."
    try:
        if title_fragment:
            candidates = [w for w in gw.getAllTitles() if title_fragment.lower() in (w or "").lower()]
            if not candidates:
                return f"No window with '{title_fragment}' found to maximize."
            win = gw.getWindowsWithTitle(candidates[0])[0]
            win.maximize()
            return f"Maximized {candidates[0]}"
        else:
            active = gw.getActiveWindow()
            if active:
                active.maximize()
                return f"Maximized {active.title}"
            return "No active window to maximize."
    except Exception as e:
        return f"Could not maximize window: {e}"

def screenshot(path=None):
    if not pyautogui:
        return "pyautogui not installed (required for screenshots)."
    try:
        if not path:
            path = os.path.join(os.path.expanduser("~"), "Desktop", f"screenshot_{int(time.time())}.png")
        img = pyautogui.screenshot()
        img.save(path)
        return f"Screenshot saved to {path}"
    except Exception as e:
        return f"Could not take screenshot: {e}"

def set_volume(percent: int):
    if not is_windows():
        return "Volume control helper currently supports Windows only."
    if AudioUtilities is None or IAudioEndpointVolume is None:
        return "Volume control libraries not installed."
    try:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        # pycaw volume range is -65.25 .. 0.0 (dB) but it provides SetMasterVolumeLevelScalar (0.0-1.0)
        scalar = max(0.0, min(1.0, percent / 100.0))
        volume.SetMasterVolumeLevelScalar(scalar, None)
        return f"Volume set to {percent}%"
    except Exception as e:
        return f"Could not set volume: {e}"

def mute_unmute():
    if not is_windows():
        return "Mute/unmute currently supports Windows only."
    if AudioUtilities is None or IAudioEndpointVolume is None:
        return "Volume control libraries not installed."
    try:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        current = volume.GetMute()
        volume.SetMute(not current, None)
        return "Muted" if not current else "Unmuted"
    except Exception as e:
        return f"Could not toggle mute: {e}"

def send_keystrokes(text):
    if not keyboard:
        return "keyboard library not installed."
    try:
        keyboard.write(text)
        return f"Typed: {text}"
    except Exception as e:
        return f"Could not type text: {e}"

def press_key(key):
    if not keyboard:
        return "keyboard library not installed."
    try:
        keyboard.send(key)
        return f"Pressed {key}"
    except Exception as e:
        return f"Could not press {key}: {e}"

def move_mouse_and_click(x, y, clicks=1, interval=0.0, button='left'):
    if not pyautogui:
        return "pyautogui not installed."
    try:
        pyautogui.moveTo(x, y, duration=0.2)
        pyautogui.click(x, y, clicks=clicks, interval=interval, button=button)
        return f"Clicked at ({x},{y})"
    except Exception as e:
        return f"Could not move/click mouse: {e}"

def open_file_or_folder(path):
    try:
        if os.path.exists(path):
            if platform.system() == "Windows":
                os.startfile(path)
            elif platform.system() == "Darwin":
                subprocess.Popen(['open', path])
            else:
                subprocess.Popen(['xdg-open', path])
            return f"Opened {path}"
        return f"Path not found: {path}"
    except Exception as e:
        return f"Could not open path: {e}"

def lock_screen():
    if is_windows():
        try:
            ctypes = __import__("ctypes")
            ctypes.windll.user32.LockWorkStation()
            return "Locking screen..."
        except Exception as e:
            return f"Could not lock screen: {e}"
    return "Lock not supported on this OS."

def shutdown(reboot=False):
    if is_windows():
        try:
            if reboot:
                subprocess.Popen(["shutdown", "/r", "/t", "3"])
                return "Rebooting system..."
            else:
                subprocess.Popen(["shutdown", "/s", "/t", "3"])
                return "Shutting down system..."
        except Exception as e:
            return f"Could not shutdown/reboot: {e}"
    else:
        try:
            if reboot:
                subprocess.Popen(["sudo", "reboot"])
                return "Rebooting system..."
            else:
                subprocess.Popen(["sudo", "poweroff"])
                return "Shutting down system..."
        except Exception as e:
            return f"Could not shutdown/reboot: {e}"

#
# ---- Main try_execute_action (keeps same signature) ----
#
def try_execute_action(command: str) -> str | None:
    command = command.lower().strip()

    # Action & info triggers
    if "open google" in command:
        open_google()
        return "Opening Google."

    elif "open gmail" in command:
        open_gmail()
        return "Opening Gmail."

    elif "open youtube" in command:
        open_youtube()
        return "Opening YouTube."

    elif "search youtube for" in command:
        query = command.split("search youtube for")[-1].strip()
        if query:
            search_youtube(query)
            return f"Searching YouTube for {query}"
        else:
            return "What should I search on YouTube?"

    elif "search google for" in command:
        query = command.split("search google for")[-1].strip()
        if query:
            return search_web(query)
        else:
            return "What would you like to search on Google?"

    elif "what time" in command :
        return tell_time()

    elif "what date is" in command or "today's date" in command:
        return tell_date()

    elif "open" in command and any(app in command for app in ["notepad", "calculator", "explorer"]):
        app_name = next(app for app in ["notepad", "calculator", "explorer"] if app in command)
        return open_app(app_name)

    # new: open specific app or path (e.g. "open vs code" or "open C:\Users\Me\file.txt")
    elif command.startswith("open "):
        target = command.split("open ", 1)[1].strip()
        # if it looks like a path
        if os.path.exists(target):
            return open_file_or_folder(target)
        # try to open installed app by name
        return open_app(target)

    elif "tell me a joke" in command or "joke" in command:
        return tell_joke()

    elif "system info" in command or "show my pc stats" in command:
        return get_system_info()

    elif "weather" in command:
        words = command.split()
        if "in" in words:
            idx = words.index("in")
            city = ' '.join(words[idx+1:])
            return tell_weather(city)
        else:
            return "Please specify a city for weather info!"

    elif "remind me to" in command:
        reminder = command.split("remind me to")[-1].strip()
        if reminder:
            return set_reminder(reminder)
        else:
            return "What should I remind you about?"

    elif "play music" in command or "play song" in command:
        if "play music" in command:
            song = command.split("play music")[-1].strip()
        else:
            song = command.split("play song")[-1].strip()
        return play_music(song)

    # ---- Window & input automation commands ----
    elif "list windows" in command or "show windows" in command:
        return list_windows()

    elif command.startswith("switch to "):
        fragment = command.split("switch to ", 1)[1].strip()
        return switch_to_window(fragment)

    elif command.startswith("close window") or command.startswith("close "):
        # "close window chrome" or "close chrome"
        fragment = None
        parts = command.split()
        if len(parts) > 1:
            fragment = command.replace("close window", "").replace("close", "").strip()
        return close_window(fragment)

    elif "minimize" in command:
        fragment = command.replace("minimize", "").replace("minimise", "").strip()
        fragment = fragment or None
        return minimize_window(fragment)

    elif "maximize" in command or "full screen" in command:
        fragment = command.replace("maximize", "").replace("full screen", "").strip()
        fragment = fragment or None
        return maximize_window(fragment)

    elif "screenshot" in command or "take screenshot" in command:
        # optionally allow "screenshot to <path>"
        if "to " in command:
            path = command.split("to ", 1)[1].strip()
            return screenshot(path)
        return screenshot()

    elif ("set volume to" in command) or ("volume to" in command):
        import re
        m = re.search(r"(\d{1,3})", command)
        if m:
            try:
                percent = int(m.group(1))
                percent = max(0, min(100, percent))
                return set_volume(percent)
            except Exception as e:
                return f"Could not set volume: {e}"
        return "Please say volume percent, for example 'Set volume to 50%.'"

    elif "mute" in command or "unmute" in command:
        return mute_unmute()

    elif command.startswith("type ") or command.startswith("write "):
        text = command.split(" ", 1)[1]
        return send_keystrokes(text)

    elif command.startswith("press "):
        key = command.split("press ", 1)[1].strip()
        return press_key(key)

    elif command.startswith("click at ") or command.startswith("click "):
        # click at x,y  or click 100,200
        try:
            coords = command.split("at", 1)[1].strip() if "at" in command else command.split(" ", 1)[1].strip()
            coords = coords.replace("(", "").replace(")", "")
            x_str, y_str = coords.split(",")
            x, y = int(x_str.strip()), int(y_str.strip())
            return move_mouse_and_click(x, y)
        except Exception as e:
            return f"Could not parse click coordinates: {e}"

    elif command.startswith("open folder ") or command.startswith("open file "):
        path = command.split(" ", 2)[2].strip()
        return open_file_or_folder(path)

    elif "lock screen" in command:
        return lock_screen()

    elif "shutdown" in command or "turn off" in command:
        # WARNING: destructive, consider voice confirmation in UI before executing
        return shutdown(reboot=False)

    elif "restart" in command or "reboot" in command:
        return shutdown(reboot=True)

    # If command is vague or not recognized, make a helpful suggestion
    if not command or command in ["help", "what can you do?", "options"]:
        return get_suggestion()

    # Generic fallback
    return None

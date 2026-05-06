# save as test_c10.py in C:\Users\punya\Project\alice\v7
import ctypes, traceback, os, sys

dll_path = r"C:\Users\punya\AppData\Local\Programs\Python\Python311\Lib\site-packages\torch\lib\c10.dll"
print("Testing DLL:", dll_path)
try:
    ctypes.WinDLL(dll_path)
    print("✅ c10.dll loaded successfully")
except OSError as e:
    print("❌ OSError while loading c10.dll:")
    print(type(e), e)
    print("\n--- Python executable ---")
    print(sys.executable)
    print("\n--- First 1200 chars of PATH ---")
    print(os.environ.get("PATH","")[:1200])
    print("\n--- End PATH snippet ---")
    traceback.print_exc()

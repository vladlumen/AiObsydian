import time
import os
from tools.sync_worker import start_sync

if __name__ == "__main__":
    path = "/mnt/c/Users/vladislav/Documents/ObsidianVault"
    observer = start_sync(path)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

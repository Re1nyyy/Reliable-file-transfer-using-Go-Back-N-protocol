import os
import threading
import time

try:
    import msvcrt
except ImportError:
    msvcrt = None


class GBNLogger:
    def __init__(self, filename, reset=False):
        self.filename = filename
        self.lock = threading.Lock()

        with self.lock:
            with _LockedLogFile(self.filename) as f:
                if reset or os.path.getsize(self.filename) == 0:
                    f.seek(0)
                    f.truncate()
                    f.write("Time, Event, Details\n".encode('utf-8'))

    def log(self, event_type, details):
        """
        event_type: 'SEND', 'RECV', 'TIMEOUT', 'DROP', etc.
        details: for example: pdu_exp=1, pdu_recv=1, status=OK
        """
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        log_entry = f"{timestamp}, {event_type}, {details}\n"
        with self.lock:
            with _LockedLogFile(self.filename) as f:
                f.seek(0, os.SEEK_END)
                f.write(log_entry.encode('utf-8'))
        print(f"[{event_type}] {details}")


class _LockedLogFile:
    def __init__(self, filename):
        self.filename = filename
        self.file = None

    def __enter__(self):
        self.file = open(self.filename, 'a+b')
        if msvcrt:
            while True:
                try:
                    self.file.seek(0)
                    msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.001)
        return self.file

    def __exit__(self, exc_type, exc, tb):
        if self.file:
            if msvcrt:
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            self.file.close()

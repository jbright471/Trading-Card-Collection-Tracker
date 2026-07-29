import os
import threading
import time
from datetime import datetime, timezone

from .pricing import refresh_collection, refresh_wishlist


class RefreshManager:
    def __init__(self, store):
        self.store = store
        self._thread = None
        self._thread_lock = threading.Lock()

    def start(self):
        with self._thread_lock:
            current = self.store.read_refresh_status()
            if current.get("state") in {"queued", "running"} and self._lock_is_active():
                return False, current
            if self.store.refresh_lock_path.exists() and not self._clear_stale_lock():
                return False, current
            try:
                descriptor = os.open(
                    self.store.refresh_lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                )
            except FileExistsError:
                return False, self.store.read_refresh_status()
            os.write(descriptor, str(os.getpid()).encode("ascii"))
            os.close(descriptor)
            status = {
                "state": "queued",
                "phase": "starting",
                "current": 0,
                "total": 0,
                "message": "Preparing refresh",
                "started_at": _now(),
                "completed_at": None,
            }
            self.store.save_refresh_status(status)
            self._thread = threading.Thread(target=self._run, daemon=True, name="tcg-refresh")
            self._thread.start()
            return True, status

    def _run(self):
        try:
            entries = self.store.read_entries()
            wishlist = self.store.read_wishlist(limit=0)
            collection_total = len(entries)
            grand_total = collection_total + len(wishlist)
            self._status("running", "collection", 0, grand_total, "Refreshing collection")

            def collection_progress(current, total, message):
                self._status("running", "collection", current, grand_total, message)

            state = refresh_collection(self.store, progress=collection_progress)

            def wishlist_progress(current, total, message):
                self._status(
                    "running", "wishlist", collection_total + current, grand_total, message
                )

            wishlist_state = refresh_wishlist(self.store, progress=wishlist_progress)
            result = {
                "total_value": state.get("total_value"),
                "failures": len(state.get("failures", [])),
                "history_updated": state.get("history_updated"),
                "history_note": state.get("history_note"),
                "wishlist_updated": len(wishlist_state.get("items", [])),
                "wishlist_failures": len(wishlist_state.get("failures", [])),
                "notifications": len(wishlist_state.get("notifications", [])),
            }
            self.store.save_refresh_status(
                {
                    "state": "complete",
                    "phase": "complete",
                    "current": grand_total,
                    "total": grand_total,
                    "message": "Refresh complete",
                    "started_at": self.store.read_refresh_status().get("started_at"),
                    "completed_at": _now(),
                    "result": result,
                }
            )
        except Exception as exc:
            self.store.save_refresh_status(
                {
                    "state": "error",
                    "phase": "error",
                    "current": self.store.read_refresh_status().get("current", 0),
                    "total": self.store.read_refresh_status().get("total", 0),
                    "message": str(exc),
                    "started_at": self.store.read_refresh_status().get("started_at"),
                    "completed_at": _now(),
                }
            )
        finally:
            self.store.refresh_lock_path.unlink(missing_ok=True)

    def _status(self, state, phase, current, total, message):
        previous = self.store.read_refresh_status()
        self.store.save_refresh_status(
            {
                "state": state,
                "phase": phase,
                "current": current,
                "total": total,
                "message": message,
                "started_at": previous.get("started_at") or _now(),
                "completed_at": None,
            }
        )

    def _lock_is_active(self):
        return self.store.refresh_lock_path.exists() and not self._clear_stale_lock()

    def _clear_stale_lock(self):
        try:
            age = time.time() - self.store.refresh_lock_path.stat().st_mtime
        except OSError:
            return True
        if age <= 20 * 60:
            return False
        self.store.refresh_lock_path.unlink(missing_ok=True)
        return True


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

"""Is the internet up? Lets the site and database clients ride out a Wi-Fi or
hotspot drop instead of mistaking it for "no more results"."""

import socket
import time

CHECK_EVERY = 60          # seconds between checks while offline


def online():
    """True if the Mac can look up and reach a well-known site."""
    for host in ("www.google.com", "www.cloudflare.com"):
        try:
            socket.create_connection((host, 443), timeout=5).close()
            return True
        except OSError:
            continue
    return False


def wait_until_online(limit, log=None, sleep=time.sleep):
    """Wait up to `limit` seconds for the internet. True if it came back."""
    if log:
        log(f"  the internet seems to be down; waiting up to {limit // 60:.0f} min for it to come back")
    t0 = time.time()
    while not online():
        if time.time() - t0 >= limit:
            return False
        sleep(CHECK_EVERY)
    if log:
        log(f"  internet is back after {(time.time() - t0) / 60:.0f} min; carrying on")
    return True

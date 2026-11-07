"""A single sampler shared by all browser clients."""
import copy
import platform
import threading
import time
from collections import deque

import psutil


def rates(previous, current, elapsed):
    return [max(0, b - a) / max(elapsed, 0.001) for a, b in zip(previous, current)]


class Collector:
    def __init__(self):
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.history = deque(maxlen=120)
        self.data = None
        self.previous = None
        self.processes = {}
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self):
        self.sample()
        self.thread.start()

    def run(self):
        while not self.stop.wait(1):
            try:
                self.sample()
            except (OSError, psutil.Error):
                # Keep the previous snapshot; its timestamp exposes stale data.
                continue

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.data)

    def sample(self):
        now = time.monotonic()
        net = psutil.net_io_counters()
        totals = (net.bytes_recv, net.bytes_sent)
        speed = rates(self.previous[1], totals, now - self.previous[0]) if self.previous else [0, 0]
        self.previous = (now, totals)
        cores = psutil.cpu_percent(percpu=True)
        cpu = round(sum(cores) / max(len(cores), 1), 1)
        mem = psutil.virtual_memory()
        disks, seen = [], set()
        for partition in psutil.disk_partitions():
            if partition.device in seen:
                continue
            try:
                usage = psutil.disk_usage(partition.mountpoint)
            except (OSError, psutil.Error):
                continue
            seen.add(partition.device)
            disks.append(dict(path=partition.mountpoint, total=usage.total, used=usage.used, percent=usage.percent))
        rows, alive = [], {}
        for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'create_time']):
            try:
                key = (proc.pid, proc.info['create_time'])
                tracked = self.processes.get(key, proc)
                load = tracked.cpu_percent() / max(psutil.cpu_count() or 1, 1)
                alive[key] = tracked
                rows.append(dict(pid=proc.pid, name=proc.info['name'] or '—', cpu=round(load, 1), memory=proc.info['memory_info'].rss))
            except (psutil.Error, OSError, AttributeError):
                continue
        self.processes = alive
        temperature = None
        try:
            sensors = psutil.sensors_temperatures()
            values = [s.current for group in sensors.values() for s in group if s.current is not None]
            temperature = max(values) if values else None
        except (AttributeError, OSError, psutil.Error):
            pass
        point = dict(time=time.time(), cpu=cpu, memory=mem.percent, down=speed[0], up=speed[1])
        self.history.append(point)
        data = dict(**point, cores=cores, memory_used=mem.used, memory_total=mem.total,
                    disks=disks, processes=sorted(rows, key=lambda p: (p['cpu'], p['memory']), reverse=True)[:15],
                    temperature=temperature, uptime=max(0, time.time() - psutil.boot_time()),
                    system=f'{platform.system()} {platform.release()}', hostname=platform.node(),
                    history=list(self.history))
        with self.lock:
            self.data = data

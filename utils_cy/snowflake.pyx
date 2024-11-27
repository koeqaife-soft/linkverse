# snowflake.pyx
from libc.stdlib cimport malloc, free
from libc.time cimport time
import time as py_time
from typing import Tuple, Union
import threading

from core import get_proc_identity


cdef class AtomicLong:
    cdef long value
    cdef object lock

    def __init__(self, long initial_value=0):
        self.value = initial_value
        self.lock = threading.Lock()

    cpdef increment(self):
        with self.lock:
            self.value += 1
            return self.value

    cpdef reset(self):
        with self.lock:
            self.value = 0

    cpdef long get_value(self):
        with self.lock:
            return self.value


cdef class SnowflakeGeneration:
    cdef long epoch
    cdef int counter_bits
    cdef int sid_bits
    cdef int pid_bits
    cdef long last_timestamp
    cdef AtomicLong counter
    cdef int pid
    cdef int server_id

    def __init__(self, int server_id=1, pid=None):
        self.epoch = 1725513600000
        self.counter_bits = 12
        self.sid_bits = 5
        self.pid_bits = 5
        self.last_timestamp = -1
        self.counter = AtomicLong()
        if pid is not None:
            self.pid = pid
        else:
            self.pid = get_proc_identity()
        self.server_id = server_id

    cpdef long generate(self):
        cdef int cb = self.counter_bits
        cdef int pb = self.pid_bits
        cdef int sb = self.sid_bits
        cdef int sid = self.server_id
        cdef int p = self.pid

        cdef long ts = <long>(py_time.time() * 1000) - self.epoch

        if ts == self.last_timestamp:
            if self.counter.increment() == (1 << cb):
                self.counter.reset()
                while ts <= self.last_timestamp:
                    ts = <long>(py_time.time() * 1000) - self.epoch
        else:
            self.counter.reset()

        self.last_timestamp = ts

        cdef int _pid = p & ((1 << pb) - 1)

        cdef long snowflake_id = (
            (ts << (cb + sb + pb)) |
            (_pid << (cb + sb)) |
            (sid << cb) |
            self.counter.get_value()
        )

        return snowflake_id

    def parse(self, snowflake_id: Union[int, str]) -> Tuple[float, int, int, int]:
        cdef long snow_id
        if isinstance(snowflake_id, str):
            snow_id = int(snowflake_id)
        else:
            snow_id = snowflake_id

        cdef int cb = self.counter_bits
        cdef int pb = self.pid_bits
        cdef int sb = self.sid_bits
        cdef long epoch = self.epoch

        cdef long timestamp = (
            (snow_id >> (cb + sb + pb)) + epoch
        )
        cdef int unique = (
            (snow_id >> (cb + sb)) & ((1 << pb) - 1)
        )
        cdef int server_id = (snow_id >> cb) & ((1 << sb) - 1)
        cdef int counter = snow_id & ((1 << cb) - 1)

        return (timestamp / 1000.0, server_id, unique, counter)

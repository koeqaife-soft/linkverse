from libc.time cimport time
cdef extern from "pthread.h":
    ctypedef struct pthread_mutex_t:
        pass
    int pthread_mutex_init(pthread_mutex_t *mutex, void *attr)
    int pthread_mutex_destroy(pthread_mutex_t *mutex)
    int pthread_mutex_lock(pthread_mutex_t *mutex)
    int pthread_mutex_unlock(pthread_mutex_t *mutex)
from typing import Tuple, Union

cdef long get_current_time_ms() nogil:
    return <long>(time(NULL) * 1000)

from core import get_proc_identity


cdef class AtomicLong:
    cdef long value

    def __cinit__(self, long initial_value=0):
        self.value = initial_value

    cpdef long increment(self):
        cdef long old_value
        old_value = self.value
        self.value += 1
        return old_value

    cpdef long get_value(self):
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

        cdef long ts = <long>(get_current_time_ms()) - self.epoch

        if ts == self.last_timestamp:
            if self.counter.increment() == (1 << cb):
                self.counter = AtomicLong()
                with nogil:
                    while ts <= self.last_timestamp:
                        ts = <long>(get_current_time_ms()) - self.epoch
        else:
            self.counter = AtomicLong()

        self.last_timestamp = ts
        cdef long snowflake_id
        cdef int _pid
        cdef long _counter = self.counter.get_value()

        with nogil:
            _pid = p & ((1 << pb) - 1)
            snowflake_id = (
                (ts << (cb + sb + pb)) |
                (_pid << (cb + sb)) |
                (sid << cb) |
                _counter
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
        cdef long timestamp
        cdef int unique
        cdef int server_id
        cdef int counter

        with nogil:
            timestamp = (
                (snow_id >> (cb + sb + pb)) + epoch
            )
            unique = (
                (snow_id >> (cb + sb)) & ((1 << pb) - 1)
            )
            server_id = (snow_id >> cb) & ((1 << sb) - 1)
            counter = snow_id & ((1 << cb) - 1)

        return (timestamp / 1000.0, server_id, unique, counter)

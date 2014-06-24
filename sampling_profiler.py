"""CPU profiler that works by sampling the call stack periodically.

This profiler provides a very simplistic view of where your request is spending
its time. It does this by periodically sampling your request's call stack to
figure out in which functions real time is being spent.

PRO: since the profiler only samples the call stack occasionally, it has much
less overhead than an instrumenting profiler, and avoids biases that
instrumenting profilers have due to instrumentation overhead (which causes
instrumenting profilers to overstate how much time is spent in frequently
called functions, or functions with deep call stacks).

CON: since the profiler only samples, it does not allow you to accurately
answer a question like, "how much time was spent in routine X?", especially if
routine X takes relatively little time.  (You *can* answer questions like "what
is the ratio of time spent in routine X vs routine Y," at least if both
routines take a reasonable amount of time.)  It is better suited for answering
the question, "Where is the time spent by my app?"
"""

from collections import defaultdict
import logging
import sys
import time
import threading

from . import util


def get_memory():
    if util.dev_server:
        try:
            # This will work in a dev shell, but will raise an error on
            # a dev server.  We convert to MB for consistency with prod.
            #
            # TODO(benkraft): Hack the dev server to allow the import.
            # It prohibits any import that wouldn't be allowed on prod,
            # but here we would actually like to be able to do the
            # import anyway, since we already do things differently on
            # prod.
            #
            # TODO(benkraft): Craig thinks the live runtime API is
            # actually reporting VSS, not RSS, so maybe we should use
            # that for consistency.  Better yet, use both.
            import resource
            return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.
        except:
            return 0
    else:
        # This will work anywhere, but will return 0 on dev.  It involves an RPC.
        return runtime.memory_usage().current()


class InspectingThread(threading.Thread):
    """Thread that periodically triggers profiler inspections."""
    SAMPLES_PER_SECOND = 250

    def __init__(self, profile=None):
        super(InspectingThread, self).__init__()
        self._stop_event = threading.Event()
        self.profile = profile

    def stop(self):
        """Signal the thread to stop and block until it is finished."""
        # http://stackoverflow.com/questions/323972/is-there-any-way-to-kill-a-thread-in-python
        self._stop_event.set()
        self.join()

    def should_stop(self):
        return self._stop_event.is_set()

    def run(self):
        """Start periodic profiler inspections.
        
        This will run, periodically inspecting and then sleeping, until
        manually stopped via stop().

        We try to "stay on schedule" by keeping track of the time we should be
        at and sleeping until that time. This means that if we stop running for
        a while due to context switching or other pauses, we'll start sampling
        faster to catch up, so we'll get the right number of samples in the
        end, but the samples may not be perfectly even."""

        next_sample_time_seconds = time.time()
        sample_number = 0

        # Keep sampling until this thread is explicitly stopped.
        while not self.should_stop():
            # Take a sample of the main request thread's frame stack...
            self.profile.take_sample(sample_number)
            sample_number += 1

            # ...then sleep and let it do some more work.
            next_sample_time_seconds += (
                1.0 / InspectingThread.SAMPLES_PER_SECOND)
            seconds_to_sleep = next_sample_time_seconds - time.time()
            if seconds_to_sleep > 0:
                time.sleep(seconds_to_sleep)


class ProfileSample(object):
    """Single stack trace sample gathered during a periodic inspection."""
    def __init__(self, stack_trace, timestamp_ms):
        # stack_trace should be a list of (filename, line_num, function_name)
        # triples.
        self.stack_trace = stack_trace
        self.timestamp_ms = timestamp_ms

    @staticmethod
    def from_frame_and_timestamp(active_frame, timestamp_ms):
        """Creates a profile from the current frame of a particular thread.

        The "active_frame" parameter should be the current frame from some
        thread, as returned by sys._current_frames(). Note that we must walk
        the stack trace up-front at sampling time, since it will change out
        from under us if we wait to access it."""
        stack_trace = []
        frame = active_frame
        while frame is not None:
            code = frame.f_code
            stack_trace.append(
                (code.co_filename, frame.f_lineno, code.co_name))
            frame = frame.f_back

        return ProfileSample(stack_trace, timestamp_ms)

    def get_frame_descriptions(self):
        """Gets a list of text descriptions, one for each frame, in order."""
        return ["%s:%s (%s)" % file_line_func
                for file_line_func in self.stack_trace]


class Profile(object):
    """Profiler that periodically inspects a request and logs stack traces.

    If memory_sample_rate is nonzero, approximately that many samples per
    second will also profile current memory usage.  Note that on prod, this
    involves an RPC, so running more than 5 or 10 samples per second is not
    recommended.
    """
    def __init__(self, memory_sample_rate=0):
        # Every self.memory_sample_every'th sample will also record memory.  We
        # want this to be such that this will add up to memory_sample_rate
        # samples per second (approximately).
        if memory_sample_rate:
            self.memory_sample_every = max(1, int(round(
                InspectingThread.SAMPLES_PER_SECOND / memory_sample_rate)))
        else:
            self.memory_sample_every = 0

        # All saved stack trace samples
        self.samples = []

        # All saved memory samples in MB, by timestamp_ms
        self.memory_samples = {}

        # Thread id for the request thread currently being profiled
        self.current_request_thread_id = None

        # Thread that constantly waits, inspects, waits, inspect, ...
        self.inspecting_thread = None

        self.start_time = time.time()

    def results(self):
        """Return sampling results in a dictionary for template context."""
        aggregated_calls = defaultdict(int)
        total_samples = len(self.samples)

        # Compress the results by keeping an array of all of the frame
        # descriptions (we expect that there won't be that many total of them).
        # Each actual stack trace is given as an ordered list of indexes into
        # the array of frames.
        frames = []
        frame_indexes = {}

        for sample in self.samples:
            for frame_desc in sample.get_frame_descriptions():
                if not frame_desc in frame_indexes:
                    frame_indexes[frame_desc] = len(frames)
                    frames.append(frame_desc)

        samples = [{
                "timestamp_ms": util.milliseconds_fmt(sample.timestamp_ms, 1),
                "memory_used": self.memory_samples.get(sample.timestamp_ms),
                "stack_frames": [frame_indexes[desc]
                                 for desc in sample.get_frame_descriptions()]
            } for sample in self.samples]

        # For convenience, we also send along with each sample the index
        # of the previous memory sample.
        if self.memory_sample_every:
            prev_memory_sample_index = 0
            for i, sample in enumerate(samples):
                sample['prev_memory_sample_index'] = prev_memory_sample_index
                if sample['memory_used'] is not None:
                    prev_memory_sample_index = i

        return {
                "frame_names": [
                    util.short_method_fmt(frame) for frame in frames],
                "samples": samples,
                "total_samples": total_samples,
            }

    def take_sample(self, sample_number):
        timestamp_ms = (time.time() - self.start_time) * 1000
        # Look at stacks of all existing threads...
        # See http://bzimmer.ziclix.com/2008/12/17/python-thread-dumps/
        for thread_id, active_frame in sys._current_frames().items():
            # ...but only sample from the main request thread.
            # TODO(kamens): this profiler will need work if we ever
            # actually use multiple threads in a single request and want to
            # profile more than one of them.
            if thread_id == self.current_request_thread_id:
                # Grab a sample of this thread's current stack
                self.samples.append(ProfileSample.from_frame_and_timestamp(
                        active_frame, timestamp_ms))
        if self.memory_sample_every:
            if sample_number % self.memory_sample_every == 0:
                self.memory_samples[timestamp_ms] = get_memory()

    def run(self, fxn):
        """Run function with samping profiler enabled, saving results."""

        if not hasattr(threading, "current_thread"):
            # Sampling profiler is not supported in Python2.5
            logging.warn("The sampling profiler is not supported in Python2.5")
            return fxn()

        # Store the thread id for the current request's thread. This lets
        # the inspecting thread know which thread to inspect.
        self.current_request_thread_id = threading.current_thread().ident

        # Start the thread that will be periodically inspecting the frame
        # stack of this current request thread
        self.inspecting_thread = InspectingThread(profile=self)
        self.inspecting_thread.start()

        try:
            # Run the request fxn which will be inspected by the inspecting
            # thread.
            return fxn()
        finally:
            # Stop and clear the inspecting thread
            self.inspecting_thread.stop()
            self.inspecting_thread = None

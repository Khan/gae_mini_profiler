"""CPU profiler that works by sampling the call stack periodically.

This profiler provides a very simplistic view of where your request is spending
its time. It does this by periodically sampling your request's call stack to
figure out in which functions real time is being spent.

PRO: since this profiler only samples the call stack occasionally, the overhead
is negligible...even during deeply nested function calls that would cause
problems for an instrumented profiler. It also offers an opinionated, simple
view of your program's performance by simply answering the question, "where
is time being spent?"

CON: since this profiler only samples the call stack occasionally, detailed
timings of functions go out the window. You won't get accuracy from this
profiler, and running it repeatedly for the same request may produce varied
results as different call stacks will get sampled.
"""

from collections import defaultdict
import logging
import os
import sys
import time
import threading
import traceback

from gae_mini_profiler import util

_is_dev_server = os.environ["SERVER_SOFTWARE"].startswith("Devel")

class InspectingThread(threading.Thread):
    """Thread that periodically triggers profiler inspections."""
    SAMPLES_PER_SECOND = 35

    def __init__(self, profile=None):
        super(InspectingThread, self).__init__()
        self._stop_event = threading.Event()
        self.profile = profile

    def stop(self):
        """Stop this thread."""
        # http://stackoverflow.com/questions/323972/is-there-any-way-to-kill-a-thread-in-python
        self._stop_event.set()

    def is_stopped(self):
        return self._stop_event.is_set()

    def run(self):
        """Start periodic profiler inspections.
        
        This will run, periodically inspecting and then sleeping, until
        manually stopped via stop()."""
        # Keep sampling until this thread is explicitly stopped.
        while not self.is_stopped():

            # Take a sample of the main request thread's frame stack...
            self.profile.take_sample()

            # ...then sleep and let it do some more work.
            time.sleep(1.0 / InspectingThread.SAMPLES_PER_SECOND)

            # Only take one sample per thread if this is running on the
            # single-threaded dev server.
            if _is_dev_server and len(self.profile.samples) > 0:
                break


class ProfileSample(object):
    """Single stack trace sample gathered during a periodic inspection."""
    def __init__(self, stack):
        self.stack_trace = traceback.extract_stack(stack)


class Profile(object):
    """Profiler that periodically inspects a request and logs stack traces."""
    def __init__(self):
        # All saved stack trace samples
        self.samples = []

        # Thread id for the request thread currently being profiled
        self.current_request_thread_id = None

        # Thread that constantly waits, inspects, waits, inspect, ...
        self.inspecting_thread = None

    def results(self):
        """Return sampling results in a dictionary for template context."""
        aggregated_calls = defaultdict(int)
        total_samples = len(self.samples)

        for sample in self.samples:
            for filename, line_num, function_name, src in sample.stack_trace:
                aggregated_calls["%s\n\n%s:%s (%s)" %
                        (src, filename, line_num, function_name)] += 1

        # Turn aggregated call samples into dictionary of results
        calls = [{
            "func_desc": item[0],
            "func_desc_short": util.short_method_fmt(item[0]),
            "count_samples": item[1],
            "per_samples": "%s%%" % util.decimal_fmt(
                100.0 * item[1] / total_samples),
            } for item in aggregated_calls.items()]

        # Sort call sample results by # of times calls appeared in a sample
        calls = sorted(calls, reverse=True,
            key=lambda call: call["count_samples"])

        return {
                "calls": calls,
                "total_samples": total_samples,
                "is_dev_server": _is_dev_server,
            }

    def take_sample(self):
        # Look at stacks of all existing threads...
        for thread_id, stack in sys._current_frames().items():

            # ...and choose to sample only the main request thread.
            # TODO(kamens): this profiler will need work if we ever actually
            # use multiple threads in a single request and want to profile more
            # than one of them.
            should_sample = thread_id == self.current_request_thread_id

            # Dev server's threading.current_thread() implementation won't give
            # us a thread id that we can use. Instead, just take a peek at the
            # stack's current package to figure out which is the request
            # thread.
            if (_is_dev_server and
                    stack.f_globals["__package__"] == "gae_mini_profiler"):
                should_sample = True

            if should_sample:
                # Grab a sample of this thread's current stack
                self.samples.append(ProfileSample(stack))

    def run(self, fxn):
        """Run function with samping profiler enabled, saving results."""
        if not hasattr(threading, "current_thread"):
            # Sampling profiler is not supported in Python2.5
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

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

import collections
import json
import logging
import sys
import time
import threading
from google.appengine.api import runtime

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

    def __init__(self, profile=None, time_fxn=time.time):
        super(InspectingThread, self).__init__()
        self._stop_event = threading.Event()
        self.profile = profile
        self.time_fxn = time_fxn

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

        next_sample_time_seconds = self.time_fxn()
        sample_number = 0

        # Keep sampling until this thread is explicitly stopped.
        while not self.should_stop():
            # Take a sample of the main request thread's frame stack...
            self.profile.take_sample(sample_number)
            sample_number += 1

            # ...then sleep and let it do some more work.
            next_sample_time_seconds += (
                1.0 / InspectingThread.SAMPLES_PER_SECOND)
            seconds_to_sleep = (
                next_sample_time_seconds - self.time_fxn())
            if seconds_to_sleep > 0:
                time.sleep(seconds_to_sleep)

        # Always take a sample at the end.
        self.profile.take_sample(sample_number, force_memory=True)


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
            stack_trace.append((code, frame.f_lineno))
            frame = frame.f_back

        return ProfileSample(stack_trace, timestamp_ms)

    def get_frame_descriptions(self):
        """Gets a list of text descriptions, one for each frame, in order."""
        return ["%s:%s (%s)" % (code.co_filename, lineno, code.co_name)
                for code, lineno in self.stack_trace]


class Profile(object):
    """Profiler that periodically inspects a request and logs stack traces.

    If memory_sample_rate is nonzero, approximately that many samples per
    second will also profile current memory usage.  Note that on prod, this
    involves an RPC, so running more than 5 or 10 samples per second is not
    recommended.

    If time_fxn is provided, it will be used instead of time.time().  This is
    useful, for example, if time.time() has been mocked out in tests.
    """
    def __init__(self, memory_sample_rate=0, time_fxn=time.time):
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
        self.memory_samples = collections.OrderedDict()

        # Thread id for the request thread currently being profiled
        self.current_request_thread_id = None

        # Thread that constantly waits, inspects, waits, inspect, ...
        self.inspecting_thread = None

        self.time_fxn = time_fxn
        self.start_time = time_fxn()

    def results(self):
        """Return sampling results in a dictionary for template context."""
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
        # of the previous and next memory samples.
        if self.memory_sample_every:
            Profile.annotate_prev_samples(samples, 'prev_memory_sample_index')
            Profile.annotate_prev_samples(samples, 'next_memory_sample_index',
                                          rev=True)

        results = {
                "frame_names": [
                    util.short_method_fmt(frame) for frame in frames],
                "samples": samples,
                "total_samples": total_samples,
            }

        if self.memory_sample_every and self.memory_samples:
            results.update({
                "start_memory": round(self.memory_samples.values()[0], 2),
                "max_memory": round(max(self.memory_samples.values()), 2),
                "end_memory": round(self.memory_samples.values()[-1], 2),
            })

        return results

    def cpuprofile_results(self):
        """Outputs profiling data in a format suitable for display in Chrome.

        They can then be loaded into the Chrome profiler and viewed there.

        The Chrome .cpuprofile format is a JSON object.  It doesn't seem to be
        documented anywhere, so here's a bit of documentation:
            The JSON root should be an object with the following keys:
                * startTime: seconds, with 6 decimals
                * endTime: likewise
                * head: a frame
                * samples: a array of the id of each sample
                * timestamps: a array of the timestamps of the samples
                    (optional, will be interpolated if missing, ignored in
                    Chrome < 36.0)

            Each frame is an object with the following keys:
                * functionName,
                * scriptId: a string, which somehow sets the URL, I think based
                    on the scripts on the current page (optional)
                * url: a URL (seems to sometimes be ignored for unknown
                    reasons, optional)
                * lineNumber: first line of function (optional)
                * columnNumber: (optional)
                * hitCount: ostensibly, the number of samples in which this is
                    the top frame.  This gets divided by the total hitCount
                    across the entire profile, and scaled to the total time.
                * callUID: a unique ID for the function
                * children: an array of frames (can be empty)
                * deoptReason: a string to be displayed as a reason this isn't
                    optimized (optional, can be empty)
                * id: a number, generally in depth-first order
        """
        if not self.samples:
            return "{}"
        call_tree, sample_ids = Profile._call_tree(self.samples)
        return json.dumps({
            "startTime": self.samples[0].timestamp_ms / 1000 + 0.01,
            "endTime": self.samples[-1].timestamp_ms / 1000,
            "head": Profile._munge_call_tree(None, call_tree),
            "samples": sample_ids,
            "timestamps": [sample.timestamp_ms * 1000
                           for sample in self.samples],
        })

    @staticmethod
    def _call_tree(samples):
        """Build a call tree for sampled stacks.  Used by cpuprofile_results.

        Returns a tuple of the root "frame" dict and a list of the id of each
        sample.  Each frame is a dict, with keys "total_time" (a number),
        "children" (a dict of function tuples (filename, line, function) ->
        frames), and "id" (an integer).
        """
        root = {
            "total_time": 0,
            "children": {},
            "id": 1,
        }
        next_id = 2
        last_sample_ms = None
        sample_ids = []
        for sample in samples:
            frame_to_add_to = root
            for frame in reversed(sample.stack_trace):
                if frame not in frame_to_add_to["children"]:
                    # If we haven't seen this frame before, add it.
                    frame_to_add_to["children"][frame] = {
                        "total_time": 0,
                        "children": {},
                        "id": next_id,
                    }
                    next_id += 1
                frame_to_add_to = frame_to_add_to["children"][frame]
            # Now frame_to_add_to is the top frame of our stack, so account for
            # the time spent in this frame in it.
            if last_sample_ms is None:
                # Make something up for the first sample, because Chrome thinks
                # of samples as taking time, and we think of them as points in
                # time.
                # TODO(benkraft): do something smarter here.
                dt = 1000.0 / InspectingThread.SAMPLES_PER_SECOND
            else:
                dt = sample.timestamp_ms - last_sample_ms
            frame_to_add_to["total_time"] += dt
            last_sample_ms = sample.timestamp_ms
            sample_ids.append(frame_to_add_to["id"])

        return root, sample_ids

    @staticmethod
    def _munge_call_tree(current_frame, call_tree):
        """Munges the call tree in _call_tree for cpuprofile_results.

        "call_tree" should be a node of the call tree returned by _call_tree,
        with all its children, and current_frame should be the (filename, line,
        function) tuple of the frame it represents.
        """
        if current_frame is None:
            call_uid = 0
            name = '(root)'
            url = ''
            lineno = 0
        else:
            code, _ = current_frame
            # (We're assuming that each function has a single shared code
            # object; we could also hash the function and file names to achieve
            # a similar effect.)
            call_uid = id(code)
            name = code.co_name
            url = "file://%s" % code.co_filename
            lineno = code.co_firstlineno

        return {
            "functionName": name,
            "url": url,
            "lineNumber": lineno,
            "hitCount": call_tree["total_time"],
            "callUID": call_uid,
            "id": call_tree["id"],
            "children": [
                Profile._munge_call_tree(frame, child_tree)
                for frame, child_tree in call_tree["children"].iteritems()],
        }

    @staticmethod
    def annotate_prev_samples(samples, key, rev=False):
        """Annotate samples with the index of the previous/next memory sample.

        For each sample in samples, if there is a previous memory sample, put
        the index of the most recent one in samples[key].  If rev, instead use
        the next one.
        """
        if not rev:
            iterator = enumerate(samples)
        else:
            # Apparently Python can't reverse an enumerate iterator directly.
            iterator = reversed(list(enumerate(samples)))
        prev_index = None
        for i, sample in iterator:
            if prev_index is not None:
                sample[key] = prev_index
            if sample['memory_used'] is not None:
                prev_index = i

    def take_sample(self, sample_number, force_memory=False):
        timestamp_ms = (self.time_fxn() - self.start_time) * 1000
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
            if force_memory or sample_number % self.memory_sample_every == 0:
                self.memory_samples[timestamp_ms] = get_memory()

    def start(self):
        """Start profiling."""
        if not hasattr(threading, "current_thread"):
            # Sampling profiler is not supported in Python2.5
            logging.warn("The sampling profiler is not supported in Python2.5")
        else:
            # Store the thread id for the current request's thread. This lets
            # the inspecting thread know which thread to inspect.
            self.current_request_thread_id = threading.current_thread().ident

            # Start the thread that will be periodically inspecting the frame
            # stack of this current request thread
            self.inspecting_thread = InspectingThread(profile=self,
                                                      time_fxn=self.time_fxn)
            self.inspecting_thread.start()

    def stop(self):
        """Stop profiling."""
        if hasattr(self, 'inspecting_thread') and self.inspecting_thread:
            # Stop and clear the inspecting thread
            self.inspecting_thread.stop()
            self.inspecting_thread = None

    def run(self, fxn):
        """Run function with samping profiler enabled, saving results."""
        self.start()
        try:
            # Run the request fxn which will be inspected by the inspecting
            # thread.
            return fxn()
        finally:
            self.stop()

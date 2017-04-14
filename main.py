# TODO(colin): fix these lint errors (http://pep8.readthedocs.io/en/release-1.7.x/intro.html#error-codes)
# pep8-disable:E302
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app

import profiler

application = webapp.WSGIApplication([
    ("/gae_mini_profiler/request/log", profiler.RequestLogHandler),
    ("/gae_mini_profiler/request", profiler.RequestStatsHandler),
    ("/gae_mini_profiler/shared/raw", profiler.RawSharedStatsHandler),
    ("/gae_mini_profiler/shared", profiler.SharedStatsHandler),
    ("/gae_mini_profiler/shared/cpuprofile", profiler.CpuProfileStatsHandler),
])

def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()

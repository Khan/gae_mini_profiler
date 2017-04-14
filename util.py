# TODO(colin): fix these lint errors (http://pep8.readthedocs.io/en/release-1.7.x/intro.html#error-codes)
# pep8-disable:E302
import os

# Assume if SERVER_SOFTWARE is not present in the environment at import time
# that we are in some kind of testing or development environment.
dev_server = os.environ.get("SERVER_SOFTWARE", "Devel").startswith("Devel")

def seconds_fmt(f, n=0):
    return milliseconds_fmt(f * 1000, n)

def milliseconds_fmt(f, n=0):
    return decimal_fmt(f, n)

def decimal_fmt(f, n=0):
    format = "%." + str(n) + "f"
    return format % f

def short_method_fmt(s):
    return s[s.rfind("/") + 1:]

def short_rpc_file_fmt(s):
    if not s:
        return ""
    return s[s.find("/"):]

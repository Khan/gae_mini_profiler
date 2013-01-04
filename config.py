from google.appengine.api import users

# Customize should_profile to return true whenever a request should be
# profiled.  This function will be run once per request, so make sure its
# contents are fast.


class ProfilerConfigProduction:
    @staticmethod
    def should_profile(environ):
        return True


class ProfilerConfigDevelopment:
    @staticmethod
    def should_profile(environ):
        return True

from google.appengine.api import lib_config
from google.appengine.api import users


# If using the default should_profile implementation, the profiler
# will only be enabled for requests made by the following GAE users.
enabled_profiler_emails = [
    "test@example.com",
    "test1@example.com",
]


# Customize should_profile to return true whenever a request should be profiled.
# This function will be run once per request, so make sure its contents are fast.
class ProfilerConfigProduction:
    @staticmethod
    def should_profile(environ):
        user = users.get_current_user()
        return user and user.email() in _config.ENABLED_PROFILER_EMAILS


class ProfilerConfigDevelopment:
    @staticmethod
    def should_profile(environ):
        return users.is_current_user_admin()


# see http://code.google.com/appengine/docs/python/tools/appengineconfig.html
_config = lib_config.register('gae_mini_profiler',
                              {'ENABLED_PROFILER_EMAILS': enabled_profiler_emails,
                               'ConfigProduction': ProfilerConfigProduction,
                               'ConfigDevelopment': ProfilerConfigDevelopment})

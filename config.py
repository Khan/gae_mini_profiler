from google.appengine.api import users

# If using the default should_profile implementation, the profiler
# will only be enabled for requests made by the following GAE users.
enabled_profiler_emails = [
    "test@example.com",
    "test1@example.com",
]

enable_profiler_admins = True

# Customize should_profile to return true whenever a request should be profiled.
# This function will be run once per request, so make sure its contents are fast.
def should_profile(environ):

    # Never profile calls to the profiler itself to avoid endless recursion.
    if environ["PATH_INFO"].startswith("/gae_mini_profiler/"):
        return False

    if enable_profiler_admins and users.is_current_user_admin():
        return True

    user = users.get_current_user()

    return user and user.email() in enabled_profiler_emails

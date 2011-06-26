# Google App Engine Mini Profiler

gae_mini_profiler is a quick drop-in WSGI app for your existing GAE projects. It exposes both AppStats and cProfile statistics for users of your choosing on your production site. Only requests coming from users of your choosing will be profiled, and others will not suffer any performance degradation. See screenshots and features below.

This project was heavily inspired by [mvc-mini-profiler](http://code.google.com/p/mvc-mini-profiler/).

gae_mini_profiler is [MIT licensed](http://en.wikipedia.org/wiki/MIT_License).

## Screenshots

...go here...

## Getting Started

1. Download this repository's source and copy the `gae_mini_profiler/` folder into your App Engine project's root directory.
2. Add the following two handler definitions to `app.yaml`:
<pre>
handlers:
&ndash; url: /gae_mini_profiler/static
&nbsp;&nbsp;static_dir: gae_mini_profiler/static<br/>
&ndash; url: /gae_mini_profiler/.*
&nbsp;&nbsp;script: gae_mini_profiler/main.py
</pre>
3. Modify the WSGI application you want to profile by wrapping it with the gae_mini_profiler WSGI application:
<pre>
&#35; Example of existing application
application = webapp.WSGIApplication(...existing application...)<br/>
&#35; Add the following
from gae_mini_profiler import profiler
application = profiler.ProfilerWSGIMiddleware(application)
</pre>
4. Insert the `profiler_includes` template tag below jQuery somewhere (preferably at the end of your template):
<pre>
        ...your html...
        {% profiler_includes %}
    &lt;/body&gt;
&lt;/html&gt;
</pre>
5. You're all set! Just choose the users for whom you'd like to enable profiling in `gae_mini_profiler/config.py`:
<pre>
&#35; If using the default should_profile implementation, the profiler
&#35; will only be enabled for requests made by the following GAE users.
enabled_profiler_emails = [
    "kamens@gmail.com",
]
</pre>

## Features

* Production profiling
* No performance impact for normal users
* Share with others

## Bonus

gae_mini_profiler is currently in production use at Khan Academy (http://khanacademy.org). If you make find good use of it elsewhere, be sure to let me know.
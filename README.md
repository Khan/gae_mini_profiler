# Google App Engine Mini Profiler

gae_mini_profiler is a quick drop-in WSGI app for your existing GAE projects. It exposes both AppStats and cProfile statistics for users of your choosing on your production site. Only requests coming from users of your choosing will be profiled, and others will not suffer any performance degradation. See screenshots and features below.

This project was heavily inspired by [mvc-mini-profiler](http://code.google.com/p/mvc-mini-profiler/).

## Screenshots

...go here...

## Getting Started

1. Download this repository's source and copy the `gae_mini_profiler/` folder into your App Engine project's root directory.
2. Add the following two handler definitions to `app.yaml`:
<pre>

</pre>
3. Add WSGI application
4. Insert template tag below jQuery somewhere

## Features

* Production profiling
* No performance impact for normal users
* Share with others
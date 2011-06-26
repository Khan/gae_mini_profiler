# Google App Engine Mini Profiler

gae-mini-profiler is a quick drop-in WSGI app for your existing GAE projects. It exposes both AppStats and cProfile statistics for users of your choosing on your production site. Only requests coming from users of your choosing will be profiled, and others will not suffer any performance degradation. See screenshots and features below.

This project was heavily inspired by [mvc-mini-profiler](http://code.google.com/p/mvc-mini-profiler/).

## Screenshots

...go here...

## Getting Started

1. Copy directory
2. Modify app.yaml
3. Add WSGI application
4. Insert template tag below jQuery somewhere

## Features

* Production profiling
* No performance impact for normal users
* Share with others
This approach to the embedded profile viewer was inspired by the one
taken on http://www.webpagetest.org where the Chrome DevTools
"Timeline" viewer is used to visualize a captured Chrome
timeline. This was originally based on webpagetest.org v2.15 at
https://github.com/WPO-Foundation/webpagetest/tree/WebPagetest-2.15/www/chrome

That is, static/chrome/inspector-20140603 comes directly from that
repo and version.

To update this code, you'll need to pull from either the WPT repo
above, or straight from the source they mentioned in their
timeline.php, a chromium release build:
out\Release\resources\inspector (I haven't tried this).

Then you'll need to make sure that the monkey-patching in
profile.html's patch() function and the assumptions in
DevToolsLoaded() still work. Since the chromium release builds have
minified JavaScript, your best bet is to find the corresponding source
code in the chromium repo. For the above v2.15 from webpagetest.org,
it seems that the 2023 branch of chromium matches:
http://src.chromium.org/viewvc/blink/branches/chromium/2023/Source/devtools/front_end

Particularly useful for the initial development of the patches were
profiler/CPUProfileView.js and profiler/ProfilesPanels.js:

 * http://src.chromium.org/viewvc/blink/branches/chromium/2023/Source/devtools/front_end/profiler/CPUProfileView.js?revision=175193

 * http://src.chromium.org/viewvc/blink/branches/chromium/2023/Source/devtools/front_end/profiler/ProfilesPanel.js?revision=175193

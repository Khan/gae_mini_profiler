var GaeMiniProfiler = {

    init: function(requestId, fShowImmediately) {
        // Fetch profile results for any ajax calls
        // (see http://code.google.com/p/mvc-mini-profiler/source/browse/MvcMiniProfiler/UI/Includes.js)
        jQuery(document).ajaxComplete(function (e, xhr, settings) {
            if (xhr) {
                var requestId = xhr.getResponseHeader('X-MiniProfiler-Id');
                if (requestId) {
                    var queryString = xhr.getResponseHeader('X-MiniProfiler-QS');
                    GaeMiniProfiler.fetch(requestId, queryString);
                }
            }
        });

        GaeMiniProfiler.fetch(requestId, window.location.search, fShowImmediately);
    },

    toggleEnabled: function(link) {
        var disabled = !!jQuery.cookiePlugin("g-m-p-disabled");

        jQuery.cookiePlugin("g-m-p-disabled", (disabled ? null : "1"), {path: '/'});

        jQuery(link).replaceWith("<em>" + (disabled ? "Enabled" : "Disabled") + "</em>");
    },

    appendRedirectIds: function(requestId, queryString) {
        if (queryString) {
            var re = /mp-r-id=([^&]+)/;
            var matches = re.exec(queryString);
            if (matches && matches.length) {
                var sRedirectIds = matches[1];
                var list = sRedirectIds.split(",");
                list[list.length] = requestId;
                return list;
            }
        }

        return [requestId];
    },

    fetch: function(requestId, queryString, fShowImmediately) {
        var requestIds = this.appendRedirectIds(requestId, queryString);

        jQuery.get(
                "/gae_mini_profiler/request",
                { "request_ids": requestIds.join(",") },
                function(data) {
                    GaeMiniProfilerTemplate.init(function() { GaeMiniProfiler.finishFetch(data, fShowImmediately); });
                },
                "json"
        );
    },

    finishFetch: function(data, fShowImmediately) {
        if (!data || !data.length) return;

        for (var ix = 0; ix < data.length; ix++) {

            var jCorner = this.renderCorner(data[ix]);

            if (!jCorner.data("attached")) {
                jQuery('body')
                    .append(jCorner)
                    .click(function(e) { return GaeMiniProfiler.collapse(e); });
                jCorner
                    .data("attached", true);
            }

            if (fShowImmediately)
                jCorner.find(".entry").first().click();

        }
    },

    collapse: function(e) {
        if (jQuery(".g-m-p").is(":visible")) {
            jQuery(".g-m-p").slideUp("fast");
            jQuery(".g-m-p-corner").slideDown("fast")
                .find(".expanded").removeClass("expanded");
            return false;
        }

        return true;
    },

    expand: function(elEntry, data) {
        var jPopup = jQuery(".g-m-p");

        if (jPopup.length)
            jPopup.remove();
        else
            jQuery(document).keyup(function(e) { if (e.which == 27) GaeMiniProfiler.collapse() });

        jPopup = this.renderPopup(data);
        jQuery('body').append(jPopup);

        var jCorner = jQuery(".g-m-p-corner");
        jCorner.find(".expanded").removeClass("expanded");
        jQuery(elEntry).addClass("expanded");

        jPopup
            .find(".profile-link")
                .click(function() { GaeMiniProfiler.toggleSection(this, ".profiler-details"); return false; }).end()
            .find(".rpc-link")
                .click(function() { GaeMiniProfiler.toggleSection(this, ".rpc-details"); return false; }).end()
            .find(".logs-link")
                .click(function() { GaeMiniProfiler.toggleSection(this, ".logs-details"); return false; }).end()
            .find(".callers-link")
                .click(function() { jQuery(this).parents("td").find(".callers").slideToggle("fast"); return false; }).end()
            .find(".toggle-enabled")
                .click(function() { GaeMiniProfiler.toggleEnabled(this); return false; }).end()
            .click(function(e) { e.stopPropagation(); })
            .css("left", jCorner.offset().left + jCorner.width() + 18)
            .slideDown("fast");

        var toggleLogRows = function(level) {
            var names = {10:'Debug', 20:'Info', 30:'Warning', 40:'Error', 50:'Critical'};
            jQuery('#slider .minlevel-text').text(names[level]);
            jQuery('#slider .loglevel').attr('class', 'loglevel ll'+level);
            for (var i = 10; i<=50; i += 10) {
                var rows = jQuery('tr.ll'+i);
                if (i<level)
                    rows.hide();
                else
                    rows.show();
            }
        };

        var initLevel = 10;

        if (jQuery('#slider .control').slider) {
            initLevel = 30;
            jQuery('#slider .control').slider({
                value: initLevel,
                min: 10,
                max: 50,
                step: 10,
                range: 'min',
                slide: function( event, ui ) {
                    toggleLogRows(ui.value);
                }
            });
        }

        toggleLogRows(initLevel);
    },

    toggleSection: function(elLink, selector) {

        var fWasVisible = jQuery(".g-m-p " + selector).is(":visible");

        jQuery(".g-m-p .expand").removeClass("expanded");
        jQuery(".g-m-p .details:visible").slideUp(50);

        if (!fWasVisible) {
            jQuery(elLink).parents(".expand").addClass("expanded");
            jQuery(selector).slideDown("fast", function() {

                var jTable = jQuery(this).find("table");

                if (jTable.length && !jTable.data("table-sorted")) {
                    jTable
                        .tablesorter()
                        .data("table-sorted", true);
                }

            });
        }
    },

    renderPopup: function(data) {
        if (data.logs) {
            var counts = {}
            jQuery.each(data.logs, function(i, log) {
                var c = counts[log[0]] || 0;
                counts[log[0]] = c + 1;
            });
            data.log_count = counts;
        }

        return jQuery("#profilerTemplate").tmplPlugin(data);
    },

    renderCorner: function(data) {
        if (data && data.profiler_results) {
            var jCorner = jQuery(".g-m-p-corner");

            var fFirst = false;
            if (!jCorner.length) {
                jCorner = jQuery("#profilerCornerTemplate").tmplPlugin();
                fFirst = true;
            }

            return jCorner.append(
                    jQuery("#profilerCornerEntryTemplate")
                        .tmplPlugin(data)
                        .addClass(fFirst ? "" : "ajax")
                        .click(function() { GaeMiniProfiler.expand(this, data); return false; })
                    );
        }
        return null;
    }
};

var GaeMiniProfilerTemplate = {

    template: null,

    init: function(callback) {
        jQuery.get("/gae_mini_profiler/static/js/template.tmpl", function (data) {
            if (data) {
                jQuery('body').append(data);
                callback();
            }
        });
    }

};
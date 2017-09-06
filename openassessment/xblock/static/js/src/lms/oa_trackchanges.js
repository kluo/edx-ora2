(function(window) {
    'use strict';
    /**
    Interface for TrackChanges assessment view.

    Args:
        element (DOM element): The DOM element representing the XBlock.
        server (OpenAssessment.Server): The interface to the XBlock server.
        baseView (OpenAssessment.BaseView): Container view.

    Returns:
        OpenAssessment.TrackChangesView
    **/
    var OpenAssessment = window.OpenAssessment || {};
    function TrackChangesView(element, server, baseView) {
        this.element = element;
        this.server = server;
        this.baseView = baseView;
        this.content = null;
    }

    function clearChangesHandler(e) {
        var suffix = this.id.split('_').pop();
        if (window.confirm('Are you sure you want to clear your changes?')) {
            e.data.trackers[suffix].rejectAll();
        }
    }

    TrackChangesView.prototype.enableTrackChanges = function enableTrackChanges() {
        var tracker;
        var $ = window.jQuery;
        var ice = window.ice;
        var element;
        var elements = document.querySelectorAll('[id^=track-changes-content_]');
        var trackers = [];

        if (!elements) {
            return;
        }

        for (var index = 0; index < elements.length; index++) {
            element = elements[index];

            tracker = new ice.InlineChangeEditor({
                element: element,
                handleEvents: true,
                currentUser: {id: 1, name: 'Reviewer'},
                plugins: [
                    {
                        // Track content that is cut and pasted
                        name: 'IceCopyPastePlugin',
                        settings: {
                            // List of tags and attributes to preserve when cleaning a paste
                            preserve: 'p,a[href],span[id,class]em,strong'
                        }
                    }
                ]
            });
            tracker.startTracking();
            trackers.push(tracker);

            $('#track_changes_clear_button_' + index).click({trackers: trackers}, clearChangesHandler);
        }
    };

    TrackChangesView.prototype.getEditedContent = function getEditedContent() {
        var $ = window.jQuery;
        var changeTracking = $('[id^=openassessment__peer-assessment__]');
        var editedContents = [];
        var trackChangesContent = $('[id^=track-changes-content_]', changeTracking);

        if (trackChangesContent.size() > 0) {
            for (var index = 0; index < trackChangesContent.length; index++) {
                var editedContentHtml = trackChangesContent.get(index).innerHTML;

                editedContents.push(editedContentHtml);
            }
        }
        return editedContents;
    };

    TrackChangesView.prototype.displayTrackChanges = function displayTrackChanges() {
        var view = this;
        var $ = window.jQuery;
        var editedResponse = $('.submission__answer__display__content.edited.part1', view.element);
        var gradingTitleHeader = $('[id^=openassessment__grade__] .submission__answer__display__title');
        gradingTitleHeader.wrapInner('<span class="original"></span>');
        var peerEditSelect = $('<select><option value="original">Your Unedited Submission</option></select>')
            .insertBefore(gradingTitleHeader)
            .wrap("<div class='submission__answer__display__content__peeredit__select'>");
        $('<span>Show response with: </span>').insertBefore(peerEditSelect);
        $(editedResponse).each(function() {
            var peerNumber = $(this).data('peer-num');
            $('<span class="peer' + peerNumber + '">Peer ' + peerNumber + "'s Edits</span>")
                .appendTo(gradingTitleHeader).hide();
            $('<option value="peer' + peerNumber + '">Peer ' + peerNumber + "'s Edits</option>")
                .appendTo(peerEditSelect);
        });
        $(peerEditSelect).change(function() {
            var valueSelected = $(':selected', this).val();
            $('.submission__answer__display__title span', view.element).hide();
            $('.submission__answer__display__title', view.element).children('.' + valueSelected).show();

            if (valueSelected === 'original') {
                $('.submission__answer__display__content.edited', view.element).hide();
                $('.submission__answer__display__content.original', view.element).show();
            } else {
                $('.submission__answer__display__content.original', view.element).hide();
                $('.submission__answer__display__content.edited', view.element).hide();
                $('.submission__answer__display__content.edited.' + valueSelected, view.element).show();
            }
        });
    };

    OpenAssessment.TrackChangesView = TrackChangesView;
    window.OpenAssessment = OpenAssessment;
}(window));

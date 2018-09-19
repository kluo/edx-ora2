"""
Grade step in the OpenAssessment XBlock.
"""
import copy
from lazy import lazy
import json

from django.utils.translation import ugettext as _

from xblock.core import XBlock

from openassessment.assessment.api import ai as ai_api
from openassessment.assessment.api import peer as peer_api
from openassessment.assessment.api import self as self_api
from openassessment.assessment.api import staff as staff_api
from openassessment.assessment.errors import SelfAssessmentError, PeerAssessmentError
from submissions import api as sub_api
from openassessment.assessment.models import TrackChanges

from data_conversion import create_submission_dict
from data_conversion import add_trackchanges_to_submission_dict


class GradeMixin(object):
    """Grade Mixin introduces all handlers for displaying grades

    Abstracts all functionality and handlers associated with Grades.

    GradeMixin is a Mixin for the OpenAssessmentBlock. Functions in the
    GradeMixin call into the OpenAssessmentBlock functions and will not work
    outside of OpenAssessmentBlock.

    """

    @XBlock.handler
    def render_grade(self, data, suffix=''):
        """
        Render the grade step.

        Args:
            data: Not used.

        Keyword Arguments:
            suffix: Not used.

        Returns:
            unicode: HTML content of the grade step.
        """
        # Retrieve the status of the workflow.  If no workflows have been
        # started this will be an empty dict, so status will be None.
        workflow = self.get_workflow_info()
        status = workflow.get('status')

        # Default context is empty
        context = {'xblock_id': self.get_xblock_id()}

        assessment_steps = self.assessment_steps
        # Render the grading section based on the status of the workflow
        try:
            if status == "cancelled":
                path = 'openassessmentblock/grade/oa_grade_cancelled.html'
                context['score'] = workflow['score']
            elif status == "done":
                path, context = self.render_grade_complete(workflow)
            elif status == "waiting":
                # The class "is--waiting--staff" is needed in the grade template for the javascript to
                # send focus to the correct step.
                # In the case where the user has completed all steps but is still waiting on a staff grade,
                # we want focus to go from the assessment steps to the staff grading step.
                if "staff-assessment" in assessment_steps:
                    context['is_waiting_staff'] = "is--waiting--staff"
                path, context = 'openassessmentblock/grade/oa_grade_waiting.html', context
            elif status is None:
                path = 'openassessmentblock/grade/oa_grade_not_started.html'
            else:  # status is 'self' or 'peer', which implies that the workflow is incomplete
                path, context = self.render_grade_incomplete(workflow)
        except (sub_api.SubmissionError, PeerAssessmentError, SelfAssessmentError):
            return self.render_error(self._(u"An unexpected error occurred."))
        else:
            return self.render_assessment(path, context)

    def render_grade_complete(self, workflow):
        """
        Render the grade complete state.

        Args:
            workflow (dict): The serialized Workflow model.

        Returns:
            tuple of context (dict), template_path (string)
        """
        # Peer specific stuff...
        assessment_steps = self.assessment_steps
        submission_uuid = workflow['submission_uuid']

        staff_assessment = None
        example_based_assessment = None
        self_assessment = None
        feedback = None
        peer_assessments = []
        has_submitted_feedback = False

        if "peer-assessment" in assessment_steps:
            peer_api.get_score(submission_uuid, self.workflow_requirements()["peer"])
            feedback = peer_api.get_assessment_feedback(submission_uuid)
            peer_assessments = [
                self._assessment_grade_context(peer_assessment)
                for peer_assessment in peer_api.get_assessments(submission_uuid)
            ]
            has_submitted_feedback = feedback is not None

        if "self-assessment" in assessment_steps:
            self_assessment = self._assessment_grade_context(
                self_api.get_assessment(submission_uuid)
            )

        if "example-based-assessment" in assessment_steps:
            example_based_assessment = self._assessment_grade_context(
                ai_api.get_latest_assessment(submission_uuid)
            )

        raw_staff_assessment = staff_api.get_latest_staff_assessment(submission_uuid)
        if raw_staff_assessment:
            staff_assessment = self._assessment_grade_context(raw_staff_assessment)

        feedback_text = feedback.get('feedback', '') if feedback else ''
        student_submission = sub_api.get_submission(submission_uuid)

        student_submission = create_submission_dict(student_submission, self.prompts)

        # For peer assessments add track changes peer edits to the student_submission.
        if "peer-assessment" in assessment_steps:
            student_submission = add_trackchanges_to_submission_dict(student_submission, peer_assessments)

        # We retrieve the score from the workflow, which in turn retrieves
        # the score for our current submission UUID.
        # We look up the score by submission UUID instead of student item
        # to ensure that the score always matches the rubric.
        # It's possible for the score to be `None` even if the workflow status is "done"
        # when all the criteria in the rubric are feedback-only (no options).
        score = workflow['score']

        context = {
            'score': score,
            'feedback_text': feedback_text,
            'has_submitted_feedback': has_submitted_feedback,
            'student_submission': student_submission,
            'peer_assessments': peer_assessments,
            'grade_details': self.grade_details(
                submission_uuid,
                peer_assessments=peer_assessments,
                self_assessment=self_assessment,
                example_based_assessment=example_based_assessment,
                staff_assessment=staff_assessment,
            ),
            'file_upload_type': self.file_upload_type,
            'allow_latex': self.allow_latex,
            'file_urls': self.get_download_urls_from_submission(student_submission),
            'xblock_id': self.get_xblock_id()
        }

        return ('openassessmentblock/grade/oa_grade_complete.html', context)

    def render_grade_incomplete(self, workflow):
        """
        Render the grade incomplete state.

        Args:
            workflow (dict): The serialized Workflow model.

        Returns:
            tuple of context (dict), template_path (string)
        """
        def _is_incomplete(step):
            return (
                step in workflow["status_details"] and
                not workflow["status_details"][step]["complete"]
            )

        incomplete_steps = []
        if _is_incomplete("peer"):
            incomplete_steps.append(self._("Peer Assessment"))
        if _is_incomplete("self"):
            incomplete_steps.append(self._("Self Assessment"))

        return (
            'openassessmentblock/grade/oa_grade_incomplete.html',
            {'incomplete_steps': incomplete_steps, 'xblock_id': self.get_xblock_id()}
        )

    @XBlock.json_handler
    def submit_feedback(self, data, suffix=''):
        """
        Submit feedback on an assessment.

        Args:
            data (dict): Can provide keys 'feedback_text' (unicode) and
                'feedback_options' (list of unicode).

        Keyword Arguments:
            suffix (str): Unused

        Returns:
            Dict with keys 'success' (bool) and 'msg' (unicode)

        """
        feedback_text = data.get('feedback_text', u'')
        feedback_options = data.get('feedback_options', list())

        try:
            peer_api.set_assessment_feedback({
                'submission_uuid': self.submission_uuid,
                'feedback_text': feedback_text,
                'options': feedback_options,
            })
        except (peer_api.PeerAssessmentInternalError, peer_api.PeerAssessmentRequestError):
            return {'success': False, 'msg': self._(u"Assessment feedback could not be saved.")}
        else:
            self.runtime.publish(
                self,
                "openassessmentblock.submit_feedback_on_assessments",
                {
                    'submission_uuid': self.submission_uuid,
                    'feedback_text': feedback_text,
                    'options': feedback_options,
                }
            )
            return {'success': True, 'msg': self._(u"Feedback saved.")}

    def grade_details(
            self, submission_uuid, peer_assessments, self_assessment, example_based_assessment, staff_assessment,
            is_staff=False
    ):
        """
        Returns details about the grade assigned to the submission.

        Args:
            submission_uuid (str): The id of the submission being graded.
            peer_assessments (list of dict): Serialized assessment models from the peer API.
            self_assessment (dict): Serialized assessment model from the self API
            example_based_assessment (dict): Serialized assessment model from the example-based API
            staff_assessment (dict): Serialized assessment model from the staff API
            is_staff (bool): True if the grade details are being displayed to staff, else False.
                Default value is False (meaning grade details are being shown to the learner).

        Returns:
            A dictionary with full details about the submission's grade.

        Example:
            {
                criteria: [{
                    'label': 'Test name',
                    'name': 'f78ac7d4ca1e4134b0ba4b40ca212e72',
                    'prompt': 'Test prompt',
                    'order_num': 2,
                    'options': [...]
                    'feedback': [
                        'Good job!',
                        'Excellent work!',
                    ]
                }],
                additional_feedback: [{
                }]
                ...
            }
        """
        criteria = copy.deepcopy(self.rubric_criteria_with_labels)

        def has_feedback(assessments):
            """
            Returns True if at least one assessment has feedback.

            Args:
                assessments: A list of assessments

            Returns:
                Returns True if at least one assessment has feedback.
            """
            return any(
                assessment.get('feedback', None) or has_feedback(assessment.get('individual_assessments', []))
                for assessment in assessments
            )

        max_scores = peer_api.get_rubric_max_scores(submission_uuid)
        median_scores = None
        assessment_steps = self.assessment_steps
        if staff_assessment:
            median_scores = staff_api.get_assessment_scores_by_criteria(submission_uuid)
        elif "peer-assessment" in assessment_steps:
            median_scores = peer_api.get_assessment_median_scores(submission_uuid)
        elif "example-based-assessment" in assessment_steps:
            median_scores = ai_api.get_assessment_scores_by_criteria(submission_uuid)
        elif "self-assessment" in assessment_steps:
            median_scores = self_api.get_assessment_scores_by_criteria(submission_uuid)

        for criterion in criteria:
            criterion_name = criterion['name']

            # Record assessment info for the current criterion
            criterion['assessments'] = self._graded_assessments(
                submission_uuid, criterion,
                assessment_steps,
                staff_assessment,
                peer_assessments,
                example_based_assessment,
                self_assessment,
                is_staff=is_staff,
            )

            # Record whether there is any feedback provided in the assessments
            criterion['has_feedback'] = has_feedback(criterion['assessments'])

            # Although we prevent course authors from modifying criteria post-release,
            # it's still possible for assessments created by course staff to
            # have criteria that differ from the current problem definition.
            # It's also possible to circumvent the post-release restriction
            # if course authors directly import a course into Studio.
            # If this happens, we simply leave the score blank so that the grade
            # section can render without error.
            criterion['median_score'] = median_scores.get(criterion_name, '')
            criterion['total_value'] = max_scores.get(criterion_name, '')

        return {
            'criteria': criteria,
            'additional_feedback': self._additional_feedback(
                staff_assessment=staff_assessment,
                peer_assessments=peer_assessments,
                self_assessment=self_assessment,
            ),
        }

    def _graded_assessments(
            self, submission_uuid, criterion, assessment_steps, staff_assessment, peer_assessments,
            example_based_assessment, self_assessment, is_staff=False
    ):
        """
        Returns an array of assessments with their associated grades.
        """
        def _get_assessment_part(title, feedback_title, part_criterion_name, assessment):
            """
            Returns the assessment part for the given criterion name.
            """
            if assessment:
                for part in assessment['parts']:
                    if part['criterion']['name'] == part_criterion_name:
                        part['title'] = title
                        part['feedback_title'] = feedback_title
                        return part
            return None

        # Fetch all the unique assessment parts
        criterion_name = criterion['name']
        staff_assessment_part = _get_assessment_part(
            _('Staff Grade'),
            _('Staff Comments'),
            criterion_name,
            staff_assessment
        )
        if "peer-assessment" in assessment_steps:
            peer_assessment_part = {
                'title': _('Peer Median Grade'),
                'criterion': criterion,
                'option': self._peer_median_option(submission_uuid, criterion),
                'individual_assessments': [
                    _get_assessment_part(
                        _('Peer {peer_index}').format(peer_index=index + 1),
                        _('Peer Comments'),
                        criterion_name,
                        peer_assessment
                    )
                    for index, peer_assessment in enumerate(peer_assessments)
                ],
            }
        else:
            peer_assessment_part = None
        example_based_assessment_part = _get_assessment_part(
            _('Example-Based Grade'), _('Example-Based Comments'), criterion_name, example_based_assessment
        )
        self_assessment_part = _get_assessment_part(
            _('Self Assessment Grade') if is_staff else _('Your Self Assessment'),
            _('Your Comments'),  # This is only used in the LMS student-facing view
            criterion_name,
            self_assessment
        )

        # Now collect together all the assessments
        assessments = []
        if staff_assessment_part:
            assessments.append(staff_assessment_part)
        if peer_assessment_part:
            assessments.append(peer_assessment_part)
        if example_based_assessment_part:
            assessments.append(example_based_assessment_part)
        if self_assessment_part:
            assessments.append(self_assessment_part)

        # Include points only for the first assessment
        if len(assessments) > 0:
            first_assessment = assessments[0]
            option = first_assessment['option']
            if option:
                first_assessment['points'] = option['points']

        return assessments

    def _peer_median_option(self, submission_uuid, criterion):
        """
        Returns the option for the median peer grade.

        Args:
            submission_uuid (str): The id for the submission.
            criterion (dict): The criterion in question.

        Returns:
            The option for the median peer grade.

        """
        median_scores = peer_api.get_assessment_median_scores(submission_uuid)
        median_score = median_scores.get(criterion['name'], None)

        def median_options():
            """
            Returns a list of options that should be shown to represent the median.

            Some examples:
              1. Options A=1, B=3, and C=5, a median score of 3 returns [B].
              2. Options A=1, B=3, and C=5, a median score of 4 returns [B, C].
              3. Options A=1, B=1, and C=3, a median score of 1 returns [A, B]
              4. Options A=1, B=1, C=3, and D=3, a median score of 2 return [A, B, C, D]
              5. Options A=1, B=3 and C=5, a median score of 6 returns [C]
                 Note: 5 should not happen as a median should never be out of range.
            """
            last_score = None
            median_options = []

            # Sort the options first by name and then by points, so that if there
            # are options with identical points they will sort alphabetically rather
            # than randomly. Note that this depends upon sorted being a stable sort.
            alphabetical_options = sorted(criterion['options'], key=lambda option: option['label'])
            ordered_options = sorted(alphabetical_options, key=lambda option: option['points'])

            for option in ordered_options:
                current_score = option['points']

                # If we have reached a new score, then decide what to do next
                if current_score is not last_score:

                    # If the last score we saw was already larger than the median
                    # score, then we must have collected enough so return all
                    # the median options.
                    if last_score >= median_score:
                        return median_options

                    # If the current score is exactly the median or is less,
                    # then we don't need any previously collected scores.
                    if current_score <= median_score:
                        median_options = []

                    # Update the last score to be the current one
                    last_score = current_score

                # Collect the current option in case it is applicable
                median_options.append(option)
            return median_options

        # Calculate the full list of matching options for the median, and then:
        #  - If zero or one matches are found, then just return None or the single item.
        #  - If more than one match is found, return a dict with an aggregate label,
        #  - the median score, and no explanation (it is too verbose to show an aggregate).
        options = median_options()
        if len(options) == 0:
            # If we weren't able to get a median option when there should be one, show the following message
            # This happens when there are less than must_be_graded_by assessments made for the user
            if len(criterion['options']) > 0:
                return {'label': _('Waiting for peer reviews')}
            else:
                return None
        if len(options) == 1:
            return options[0]
        return {
            'label': u' / '.join([option['label'] for option in options]),
            'points': median_score,
            'explanation': None,
        }

    def _additional_feedback(self, staff_assessment, peer_assessments, self_assessment):
        """
        Returns an array of additional feedback for the specified assessments.

        Args:
            staff_assessment: The staff assessment
            peer_assessments: An array of peer assessments
            self_assessment: The self assessment

        Returns:
            Returns an array of additional feedback per assessment.
        """
        additional_feedback = []
        if staff_assessment:
            feedback = staff_assessment.get('feedback')
            if feedback:
                additional_feedback.append({
                    'title': _('Staff Comments'),
                    'feedback': feedback
                })
        if peer_assessments and len(peer_assessments) >= self.workflow_requirements()['peer']['must_be_graded_by']:
            individual_feedback = []
            for peer_index, peer_assessment in enumerate(peer_assessments):
                individual_feedback.append({
                    'title': _('Peer {peer_index}').format(peer_index=peer_index + 1),
                    'feedback': peer_assessment.get('feedback')
                })
            if any(assessment_feedback['feedback'] for assessment_feedback in individual_feedback):
                additional_feedback.append({
                    'title': _('Peer'),
                    'individual_assessments': individual_feedback
                })
        if self_assessment:
            feedback = self_assessment.get('feedback')
            if feedback:
                additional_feedback.append({
                    'title': _('Your Comments'),
                    'feedback': feedback
                })

        return additional_feedback if additional_feedback else None

    @lazy
    def _criterion_and_option_labels(self):
        """
        Retrieve criteria and option labels from the rubric in the XBlock problem definition,
        defaulting to the name value if no label is available (backwards compatibility).

        Evaluated lazily, so it will return a cached value if called repeatedly.
        For the grade mixin, this should be okay, since we can't change the problem
        definition in the LMS (the settings fields are read-only).

        Returns:
            Tuple of dictionaries:
                `criterion_labels` maps criterion names to criterion labels.
                `option_labels` maps (criterion name, option name) tuples to option labels.

        """
        criterion_labels = {}
        option_labels = {}
        for criterion in self.rubric_criteria_with_labels:
            criterion_labels[criterion['name']] = criterion['label']
            for option in criterion['options']:
                option_label_key = (criterion['name'], option['name'])
                option_labels[option_label_key] = option['label']

        return criterion_labels, option_labels

    def _assessment_grade_context(self, assessment):
        """
        Sanitize an assessment dictionary into a format that can be
        passed into the grade complete Django template.

        Args:
            assessment (dict): The serialized assessment model.

        Returns:
            dict

        """
        assessment = copy.deepcopy(assessment)

        # Retrieve dictionaries mapping criteria/option names to the associated labels.
        # This is a lazy property, so we can call it repeatedly for each assessment.
        criterion_labels, option_labels = self._criterion_and_option_labels

        # Backwards compatibility: We used to treat "name" as both a user-facing label
        # and a unique identifier for criteria and options.
        # Now we treat "name" as a unique identifier, and we've added an additional "label"
        # field that we display to the user.
        # If criteria/options in the problem definition do NOT have a "label" field
        # (because they were created before this change),
        # we create a new label that has the same value as "name".
        if assessment is not None:
            for part in assessment['parts']:
                criterion_label_key = part['criterion']['name']
                part['criterion']['label'] = criterion_labels.get(criterion_label_key, part['criterion']['name'])

                # We need to be a little bit careful here: some assessment parts
                # have only written feedback, so they're not associated with any options.
                # If that's the case, we don't need to add the label field.
                if part.get('option') is not None:
                    option_label_key = (part['criterion']['name'], part['option']['name'])
                    part['option']['label'] = option_labels.get(option_label_key, part['option']['name'])

        # Get any track changes from the db and if there are some add them to the assessment dict for rendering.
        assessment['track_changes'] = None
        track_changes = TrackChanges.objects.filter(
            scorer_id=assessment['scorer_id'],
            owner_submission_uuid=assessment['submission_uuid'],
        )

        if track_changes:
            assessment['track_changes'] = json.loads(track_changes.get().json_edited_content)

        return assessment

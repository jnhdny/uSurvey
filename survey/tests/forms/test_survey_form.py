from datetime import date
from django.test.testcases import TestCase
from survey.forms.surveys import SurveyForm
from survey.models import Survey


class SurveyFormTest(TestCase):
    def test_should_have_name_description_type_and_sample_size_fields(self):
        survey_form = SurveyForm()

        fields = ['name', 'description', 'type', 'sample_size', 'has_sampling']

        [self.assertIn(field, survey_form.fields) for field in fields]

    def test_should_not_be_valid_if_name_field_is_empty_or_blank(self):
        survey_form = SurveyForm()
        self.assertFalse(survey_form.is_valid())

    def test_should_be_valid_if_all_fields_are_given(self):
        form_data = {'name': 'xyz',
                     'description': 'survey description',
                     'has_sampling': True,
                     'sample_size': 10,
                     'type': True,
        }

        survey_form = SurveyForm(data=form_data)
        self.assertTrue(survey_form.is_valid())

    def test_should_be_valid_if_has_sampling_is_false_and_sample_size_is_blank(self):
        form_data = {'name': 'xyz',
                     'description': 'survey description',
                     'has_sampling': False,
                     'sample_size': 0,
                     'type': True,
        }

        survey_form = SurveyForm(data=form_data)
        is_valid = survey_form.is_valid()

        print survey_form.errors
        self.assertTrue(is_valid)

    def test_should_be_invalid_if_has_sampling_is_true_and_sample_size_is_not_provided(self):
        form_data = {'name': 'xyz',
                     'description': 'survey description',
                     'has_sampling': True,
                     'type': True,
        }

        error_message = 'Sample size must be specified if has sampling is selected.'
        survey_form = SurveyForm(data=form_data)
        self.assertFalse(survey_form.is_valid())
        self.assertIn(error_message, survey_form.errors['__all__'])

    def test_form_is_not_valid_if_survey_with_same_name_exists(self):
        form_data = {'name': 'xyz',
                     'description': 'survey description',
                     'sample_size': 10,
                     'type': True,
        }

        Survey.objects.create(**form_data)

        form_data['description'] = 'survey description edited'
        form_data['sample_size'] = 20

        survey_form = SurveyForm(data=form_data)
        self.assertFalse(survey_form.is_valid())

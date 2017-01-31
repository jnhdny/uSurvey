import re
from django.core.exceptions import ValidationError
from django.forms import ModelForm
from django import forms
from survey.models import RandomizationCriterion, CriterionTestArgument, QuestionOption, ListingTemplate
from survey.models import Answer, NumericalAnswer, TextAnswer, MultiChoiceAnswer, Interview
from survey.forms.widgets import InlineRadioSelect
from survey.forms.form_order_mixin import FormOrderMixin
from survey.models import Survey, BatchCommencement, SurveyHouseholdListing, AnswerAccessDefinition, USSDAccess


class SurveyForm(ModelForm, FormOrderMixin):

    class Meta:
        model = Survey
        exclude = []
        widgets = {
            'description': forms.Textarea(attrs={"rows": 3, "cols": 40}),
            'random_sample_label': forms.Textarea(attrs={"rows": 2, "cols": 40}),
            'has_sampling': InlineRadioSelect(choices=((True, 'Sampled'), (False, 'Census')),
                                              attrs={'class': 'has_sampling'}),
        }

    def __init__(self, *args, **kwargs):
        super(SurveyForm, self).__init__(*args, **kwargs)
        if kwargs.get('instance', None) and kwargs['instance'].has_sampling is False:
            self.fields['preferred_listing'].widget.attrs[
                'disabled'] = 'disabled'
        preferred_listings = [('', '------ None, Create new -------'), ]
        try:
            listing_forms = ListingTemplate.objects.values_list('pk', flat=True).order_by('id')
            survey_listings = Interview.objects.filter(pk__in=listing_forms).only('survey').distinct('survey')
            preferred_listings.extend(
                set([(l.survey.pk, l.survey.name) for l in survey_listings]))
            self.fields['preferred_listing'].choices = preferred_listings
        except Exception, err:
            print Exception, err
        self.fields['listing_form'].required = False
        self.order_fields(['name', 'description', 'has_sampling', 'sample_size',
                           'preferred_listing', 'listing_form', 'sample_naming_convention'])

    def clean_random_sample_label(self):
        """Make sure this field makes reference to listing form entry in {{}} brackets
        :return:
        """
        if self.cleaned_data['has_sampling'] and not self.data.get('preferred_listing', None):
            pattern = '{{ *([0-9a-zA-Z_]+) *}}'
            label = self.data.get('random_sample_label', '')
            requested_identifiers = re.findall(pattern, label)
            if not requested_identifiers:
                raise ValidationError('You need to include one listing response identifier in double curly brackets'
                                      ' e.g {{house_number}}')
            listing_form = self.cleaned_data['listing_form']
            if listing_form.questions.filter(identifier__in=requested_identifiers).exists():
                return self.cleaned_data['random_sample_label']
            raise ValidationError('%s is not in %s' % (', '.join(requested_identifiers), listing_form.name))

    def clean(self):
        cleaned_data = self.cleaned_data
        has_sampling = cleaned_data.get('has_sampling', None)
        if has_sampling and not cleaned_data.get('sample_size', None):
            raise ValidationError(
                'Sample size must be specified if has sampling is selected.')
        if self.data.get('listing_form', None):
            self.cleaned_data['random_sample_label'] = self.clean_random_sample_label()
        return cleaned_data

    def clean_name(self):
        name = self.cleaned_data['name']
        survey = Survey.objects.filter(name=name)
        instance_id = self.instance.id

        if not instance_id and survey:
            raise ValidationError("Survey with name %s already exist." % name)
        elif instance_id and survey and survey[0].id != instance_id:
            raise ValidationError("Survey with name %s already exist." % name)

        return self.cleaned_data['name']


class SamplingCriterionForm(forms.ModelForm, FormOrderMixin):
    min = forms.IntegerField(required=False)
    max = forms.IntegerField(required=False)
    value = forms.CharField(required=False)
    options = forms.ChoiceField(choices=[], required=False)

    def __init__(self, survey, *args, **kwargs):
        super(SamplingCriterionForm, self).__init__(*args, **kwargs)
        self.fields['survey'].initial = survey.pk
        self.fields['survey'].widget = forms.HiddenInput()
        self.fields['listing_question'].queryset = survey.listing_form.questions.filter(answer_type__in=[
            defin.answer_type for defin in AnswerAccessDefinition.objects.filter(channel=USSDAccess.choice_name())])
        self.fields['listing_question'].empty_label = 'Code - Question'
        self.order_fields(['listing_question', 'validation_test', 'options', 'value', 'min', 'max', 'survey'])
        if self.data.get('listing_question', []):
            options = QuestionOption.objects.filter(question__pk=self.data['listing_question'])
            self.fields['options'].choices = [(opt.text, opt.text) for opt in options]

    class Meta:
        exclude = []
        model = RandomizationCriterion
    #
    # def validate_options(self):
    #     listing_question = self.cleaned_data['listing_question']
    #
    #     return self.cleaned_data['options']

    def clean(self):
        super(SamplingCriterionForm, self).clean()
        validation_test = self.cleaned_data.get('validation_test', None)
        listing_question = self.cleaned_data.get('listing_question', None)
        answer_class = Answer.get_class(listing_question.answer_type)
        method = getattr(answer_class, validation_test, None)
        if method is None:
            raise ValidationError('unsupported validator defined on listing question')
        if validation_test == 'between':
            if self.cleaned_data.get('min', False) is False or self.cleaned_data.get('max', False) is False:
                raise ValidationError('min and max values required for between condition')
        elif self.cleaned_data.get('value', False) is False:
            raise ValidationError('Value is required for %s' % validation_test)
        if listing_question and listing_question.answer_type == MultiChoiceAnswer.choice_name():
            if self.cleaned_data.get('options', False) is False:
                raise ValidationError('No option selected for %s' % listing_question.identifier)
            self.cleaned_data['value'] = self.cleaned_data['options']
        return self.cleaned_data

    def save(self, *args, **kwargs):
        criterion = super(SamplingCriterionForm, self).save(*args, **kwargs)
        criterion.arguments.all().delete()      # recreate the arguments
        if criterion.validation_test == 'between':
            criterion.arguments.create(position=0, param=self.cleaned_data['min'])
            criterion.arguments.create(position=1, param=self.cleaned_data['max'])
        else:
            criterion.arguments.create(position=0, param=self.cleaned_data.get('value', ''))
        return criterion



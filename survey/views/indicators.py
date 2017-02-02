from django.utils.datastructures import SortedDict
from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.core.urlresolvers import reverse
from survey.models import LocationType, Location
from survey.forms.indicator import IndicatorForm, IndicatorCriteriaForm
from survey.forms.filters import IndicatorFilterForm, IndicatorMetricFilterForm
from survey.models import Indicator, Survey, Answer
from survey.services.simple_indicator_service import SimpleIndicatorService
from survey.forms.enumeration_area import LocationsFilterForm


@permission_required('auth.can_view_batches')
def new(request):
    indicator_form = IndicatorForm()
    if request.method == 'POST':
        indicator_form = IndicatorForm(request.POST)
        if indicator_form.is_valid():
            indicator_form.save()
            messages.success(request, "Indicator successfully created.")
            return HttpResponseRedirect(reverse('list_indicator_page'))
        messages.error(request, "Indicator was not created.")
    request.breadcrumbs([
        ('Indicators', reverse('list_indicator_page')),
    ])
    return render(request, 'indicator/new.html',
                  {'indicator_form': indicator_form, 'title': 'Add Indicator', 'button_label': 'Create',
                   'cancel_url': reverse('list_indicator_page'), 'action': '/indicators/new/'})


def _process_form(indicator_filter_form, indicators):
    if indicator_filter_form.is_valid():
        survey_id = indicator_filter_form.cleaned_data['survey']
        batch_id = indicator_filter_form.cleaned_data['batch']
        module_id = indicator_filter_form.cleaned_data['module']
        if batch_id.isdigit() and module_id.isdigit():
            indicators = indicators.filter(batch=batch_id, module=module_id)
        elif not batch_id.isdigit() and module_id.isdigit():
            indicators = indicators.filter(module=module_id)
        elif batch_id.isdigit() and not module_id.isdigit():
            indicators = indicators.filter(batch=batch_id)
        elif survey_id.isdigit():
            batches = Survey.objects.get(id=survey_id).batches.all()
            indicators = indicators.filter(batch__in=batches)
    return indicators


@permission_required('auth.can_view_batches')
def index(request):
    indicators = Indicator.objects.all()
    indicator_filter_form = IndicatorFilterForm(data=request.GET)
    indicators = _process_form(indicator_filter_form, indicators)

    return render(request, 'indicator/index.html',
                  {'indicators': indicators, 'indicator_filter_form': indicator_filter_form})


@permission_required('auth.can_view_batches')
def delete(request, indicator_id):
    indicator = Indicator.objects.get(id=indicator_id)
    Formula.objects.filter(indicator=indicator).delete()
    indicator.delete()
    messages.success(request, 'Indicator successfully deleted.')
    return HttpResponseRedirect('/indicators/')


def edit(request, indicator_id):
    indicator = Indicator.objects.get(id=indicator_id)
    indicator_form = IndicatorForm(instance=indicator)
    if request.method == 'POST':
        indicator_form = IndicatorForm(data=request.POST, instance=indicator)
        if indicator_form.is_valid():
            indicator_form.save()
            messages.success(request, "Indicator successfully edited.")
            return HttpResponseRedirect("/indicators/")
        messages.error(request, "Indicator was not successfully edited.")
    request.breadcrumbs([
        ('Indicators', reverse('list_indicator_page')),
    ])
    context = {'indicator_form': indicator_form, 'title': 'Edit Indicator',
               'button_label': 'Save', 'cancel_url': reverse('list_indicator_page')}
    return render(request, 'indicator/new.html', context)


@permission_required('auth.can_view_household_groups')
def add_indicator_formular(request, indicator_id):
    response = None
    indicator = Indicator.get(pk=indicator_id)
    criteria_form = IndicatorCriteriaForm(indicator)
    if request.method == 'POST':
        criteria_form = IndicatorCriteriaForm(indicator, data=request.POST)
        if criteria_form.is_valid():
            criteria_form.save()
            messages.success(request, 'Criteria successfully saved.')
            return HttpResponseRedirect('.')
    context = {'criteria_form': criteria_form,
               'indicator': indicator,
               'conditions': indicator.indicator_criteria.all(),
               'title': "Manage Indicator Criteria",
               'button_label': 'Save',
               'id': 'add_group_form',
               'cancel_url': reverse('list_indicator_page'),
               'parameter_questions': indicator.parameter.e_qset.all_questions,
               'condition_title': "New Eligibility Criteria"}
    request.breadcrumbs([
        ('Indicators', reverse('list_indicator_page')),
    ])
    return response or render(request, 'indicator/indicator_formula.html', context)


@permission_required('auth.can_view_batches')
def simple_indicator(request, indicator_id):
    hierarchy_limit = 2
    selected_location = None
    report_location_type = LocationType.largest_unit()
    params = request.GET or request.POST
    locations_filter = LocationsFilterForm(data=params)
    indicator_metric_form = IndicatorMetricFilterForm(params)
    metric = int(indicator_metric_form.data['metric'])
    first_level_location_analyzed = Location.objects.filter(
        type__name__iexact="country")[0]
    indicator = Indicator.objects.get(id=indicator_id)
    formula = indicator.indicator_criteria.all()
    if not formula:
        messages.error(request, "No formula was found in this indicator")
        return HttpResponseRedirect(reverse("list_indicator_page"))
    request.breadcrumbs([
        ('Indicator List', reverse('list_indicator_page')),
    ])
    if locations_filter.last_location_selected:
        selected_location = locations_filter.last_location_selected
        # hence set the location where the report is based. i.e the child current selected location.
        report_location_type = LocationType.objects.get(parent=selected_location)
    indicator_service = SimpleIndicatorService(formula, first_level_location_analyzed)
    data_series, locations = indicator_service.get_location_names_and_data_series()
    context = {'request': request,
               'data_series': _get_data_series(selected_location, indicator, metric),
               'location_names': locations,
               'indicator': indicator,
               'locations_filter': locations_filter,
               'options': indicator.parameter.options.all(),
               'report_location_type': report_location_type,
               'indicator_metric_form': indicator_metric_form
               }
    return render(request, 'formula/simple_indicator.html', context)


def _get_data_series(location_parent, indicator, metric):
    tabulated_data = SortedDict()
    location_names = []
    options = indicator.parameter.options.order_by('order')
    answer_class = Answer.get_class(indicator.parameter.answer_type)
    first_level_locations = location_parent.get_children().order_by('name')
    for child_location in first_level_locations:
        location_names.append(child_location.name)
        loc_answers = answer_class.objects.filter(question__id=indicator.parameter.id,
                                                  interview__ea__locations__in=
                                                  child_location.get_leafnodes(include_self=True))
        factor = 1
        if metric == Indicator.PERCENTAGE:
            factor = float(100)/loc_answers.count()
        tabulated_data[child_location.name] = [loc_answers.filter(value__pk=option.pk).count()*factor
                                               for option in options]
    return tabulated_data

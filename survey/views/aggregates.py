from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from survey.models import *

from rapidsms.contrib.locations.models import Location, LocationType
from survey.views.location_widget import LocationWidget
from django.contrib import messages

def status(request):
    params = request.GET
    content = {'selected_batch': None}
    selected_location = None
    if params.has_key('location') and  params.has_key('batch'):
        selected_location = Location.objects.get(id=params['location'])
        batch = Batch.objects.get(id=params['batch'])
        households_status, cluster_status, pending_investigators = HouseholdBatchCompletion.status_of_batch(batch, selected_location)
        content = { 'selected_location': selected_location,
                    'selected_batch': batch,
                    'households': households_status,
                    'clusters': cluster_status,
                    'investigators': pending_investigators,
                  }
        if batch.is_closed_for(selected_location):
            messages.error(request, "This batch is currently closed for this location.")
    content['locations'] = LocationWidget(selected_location)
    content['batches'] = Batch.objects.all()
    return render(request, 'aggregates/status.html', content)
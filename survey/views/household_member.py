from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import render
from survey.forms.householdMember import HouseholdMemberForm
from survey.models import Household, HouseholdMember


def new(request, household_id):
    member_form = HouseholdMemberForm()

    try:
        household = Household.objects.get(id=household_id)

        if request.method == 'POST':
            member_form = HouseholdMemberForm(data=request.POST)

            if member_form.is_valid():
                household_member = member_form.save(commit=False)
                household_member.household = household
                household_member.save()
                messages.success(request, 'Household member successfully created.')
                return HttpResponseRedirect('/households/')
    except Household.DoesNotExist:
        messages.error(request, 'There are  no households currently registered  for this ID.')
        return HttpResponseRedirect('/households/')

    return render(request, 'household_member/new.html', {'member_form': member_form, 'button_label': 'Create'})


def edit(request, household_id, member_id):
    household_member = HouseholdMember.objects.get(id=member_id, household__id=household_id)
    member_form = HouseholdMemberForm(instance=household_member)

    if request.method == 'POST':
        member_form = HouseholdMemberForm(instance=household_member, data=request.POST)
        if member_form.is_valid():
            member_form.save()
            messages.success(request, 'Household member successfully edited.')
            return HttpResponseRedirect('/households/')

    return render(request, 'household_member/new.html',
                  {'member_form': member_form, 'button_label': 'Save'})
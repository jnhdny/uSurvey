from random import randint
import datetime
import urllib2

from mock import patch
from django.test import Client
from rapidsms.contrib.locations.models import Location

from survey.investigator_configs import COUNTRY_PHONE_CODE
from survey.models import Backend, Survey, Investigator, Household, Batch, RandomHouseHoldSelection, QuestionModule, HouseholdMemberGroup, QuestionOption, Question, HouseholdHead, MultiChoiceAnswer, HouseholdMember
from survey.tests.ussd.ussd_base_test import USSDBaseTest
from survey.ussd.ussd import USSD
from survey.ussd.ussd_survey import USSDSurvey


class USSDReportingNonResponseTest(USSDBaseTest):
    def setUp(self):
        self.client = Client()
        self.ussd_params = {
            'transactionId': "123344" + str(randint(1, 99999)),
            'transactionTime': datetime.datetime.now().strftime('%Y%m%dT%H:%M:%S'),
            'msisdn': '2567765' + str(randint(1, 99999)),
            'ussdServiceCode': '130',
            'ussdRequestString': '',
            'response': "false"
        }
        self.backend = Backend.objects.create(name='something')
        self.open_survey = Survey.objects.create(name="open survey", description="open survey", has_sampling=True)
        self.batch = Batch.objects.create(order=1, name="Batch A", survey=self.open_survey)
        self.kampala = Location.objects.create(name="Kampala")
        self.entebbe = Location.objects.create(name="Entebbe")

        self.investigator = Investigator.objects.create(name="investigator name",
                                                        mobile_number=self.ussd_params['msisdn'].replace(
                                                            COUNTRY_PHONE_CODE, ''),
                                                        location=self.kampala,
                                                        backend=self.backend)

        self.household1 = self.create_household(1)
        self.household2 = self.create_household(2)
        self.household3 = self.create_household(3)
        self.household4 = self.create_household(4)

        self.household_head = self.create_household_member(name="Bob", household=self.household1)

        self.none_response_group = HouseholdMemberGroup.objects.create(name="NON_RESPONSE", order=0)
        module = QuestionModule.objects.create(name='NON RESPONSE')
        self.non_response_question = Question.objects.create(module=module,
                                                             text="Why did HH-%s-%s not take the survey",
                                                             answer_type=Question.MULTICHOICE, order=1,
                                                             group=self.none_response_group)
        QuestionOption.objects.create(question=self.non_response_question, text="House closed", order=1)
        QuestionOption.objects.create(question=self.non_response_question, text="Household moved", order=2)
        QuestionOption.objects.create(question=self.non_response_question, text="Refused to answer", order=3)
        QuestionOption.objects.create(question=self.non_response_question, text="Died", order=4)

        self.member_non_response_question = Question.objects.create(module=module, text="Why did %s not take the survey",
                                                answer_type=Question.MULTICHOICE, order=2, group=self.none_response_group)
        QuestionOption.objects.create(question=self.member_non_response_question, text="Member Refused", order=1)
        QuestionOption.objects.create(question=self.member_non_response_question, text="Reason", order=2)

    def create_household(self, unique_id):
        return Household.objects.create(investigator=self.investigator, location=self.investigator.location,
                                        uid=unique_id, random_sample_number=unique_id, survey=self.open_survey)

    def create_household_member(self, name, household, head=True, date_of_birth="1990-9-9", minutes_ago=6):
        object_to_create = HouseholdHead if head else HouseholdMember
        household_member = object_to_create.objects.create(surname=name, date_of_birth=date_of_birth, household=household)
        household_member.created -= datetime.timedelta(minutes=minutes_ago)
        household_member.save()
        return household_member


    def test_shows_non_response_menu_if_its_activated(self):
        self.batch.activate_non_response_for(self.kampala)
        with patch.object(RandomHouseHoldSelection.objects, 'filter', return_value=[1]):
            with patch.object(Survey, "currently_open_survey", return_value=self.open_survey):
                with patch.object(USSDSurvey, 'is_active', return_value=False):
                    response = self.reset_session()
                    homepage = "Welcome %s to the survey.\n1:" \
                               " Register households\n2: " \
                               "Take survey\n3: " \
                               "Report non-response" % self.investigator.name
                    response_string = "responseString=%s&action=request" % homepage
                    self.assertEqual(urllib2.unquote(response.content), response_string)

    def test_does_not_show_non_response_menu_if_its_not_deactivated(self):
        self.batch.deactivate_non_response_for(self.kampala)
        with patch.object(RandomHouseHoldSelection.objects, 'filter', return_value=[1]):
            with patch.object(Survey, "currently_open_survey", return_value=self.open_survey):
                with patch.object(USSDSurvey, 'is_active', return_value=False):
                    response = self.reset_session()
                    homepage = "Welcome %s to the survey.\n1: Register households\n2: Take survey" % self.investigator.name
                    response_string = "responseString=%s&action=request" % homepage
                    self.assertEqual(urllib2.unquote(response.content), response_string)

    def test_shows_only_households_that_have_not_completed(self):
        self.household1.batch_completed(self.batch)
        self.household2.batch_completed(self.batch)
        self.household3.batch_completed(self.batch)

        self.batch.activate_non_response_for(self.kampala)
        with patch.object(RandomHouseHoldSelection.objects, 'filter', return_value=[1]):
            with patch.object(Survey, "currently_open_survey", return_value=self.open_survey):
                with patch.object(USSDSurvey, 'is_active', return_value=False):
                    self.reset_session()
                    response = self.report_non_response()
                    household_list = USSD.MESSAGES['HOUSEHOLD_LIST'] + "\n1: Household-%s" % self.household4.uid
                    first_page_list = "responseString=%s&action=request" % household_list
                    self.assertEquals(urllib2.unquote(response.content), first_page_list)

    def test_paginates_non_completed_households_list(self):
        household5 = self.create_household(5)
        household6 = self.create_household(6)
        household7 = self.create_household(7)
        household8 = self.create_household(8)
        household9 = self.create_household(9)
        household10 = self.create_household(10)

        self.household1.batch_completed(self.batch)

        self.batch.activate_non_response_for(self.kampala)
        with patch.object(RandomHouseHoldSelection.objects, 'filter', return_value=[1]):
            with patch.object(Survey, "currently_open_survey", return_value=self.open_survey):
                with patch.object(USSDSurvey, 'is_active', return_value=False):
                    self.reset_session()
                    response = self.report_non_response()
                    household_list = USSD.MESSAGES['HOUSEHOLD_LIST'] + "\n1: Household-%s" \
                                                                       "\n2: Household-%s" \
                                                                       "\n3: Household-%s" \
                                                                       "\n4: Household-%s" \
                                                                       "\n#: Next" % (
                                         self.household2.uid, self.household3.uid, self.household4.uid, household5.uid)
                    first_page_list = "responseString=%s&action=request" % household_list
                    self.assertEquals(urllib2.unquote(response.content), first_page_list)
                    response = self.respond("#")

                    household_list = USSD.MESSAGES['HOUSEHOLD_LIST'] + "\n5: Household-%s" \
                                                                       "\n6: Household-%s" \
                                                                       "\n7: Household-%s" \
                                                                       "\n8: Household-%s" \
                                                                       "\n*: Back\n#: Next" % (
                                         household6.uid, household7.uid, household8.uid, household9.uid)
                    second_page_list = "responseString=%s&action=request" % household_list
                    self.assertEquals(urllib2.unquote(response.content), second_page_list)

                    response = self.respond("#")

                    household_list = USSD.MESSAGES['HOUSEHOLD_LIST'] + "\n9: Household-%s" \
                                                                       "\n*: Back" % household10.uid
                    last_page_list = "responseString=%s&action=request" % household_list
                    self.assertEquals(urllib2.unquote(response.content), last_page_list)

                    response = self.respond("*")
                    self.assertEquals(urllib2.unquote(response.content), second_page_list)

                    response = self.respond("*")
                    self.assertEquals(urllib2.unquote(response.content), first_page_list)

    def test_shows_non_response_questions_for_non_completed_households_if_none_of_the_members_have_completed_the_survey(self):
        household_member = self.create_household_member(name="bob son", household=self.household1, head=False, date_of_birth="1996-9-9")
        self.batch.activate_non_response_for(self.kampala)
        with patch.object(RandomHouseHoldSelection.objects, 'filter', return_value=[1]):
            with patch.object(Survey, "currently_open_survey", return_value=self.open_survey):
                with patch.object(USSDSurvey, 'is_active', return_value=False):
                    self.reset_session()
                    self.report_non_response()
                    response = self.select_household()
                    non_response_option_page = "\n1: House closed\n2: Household moved\n3: Refused to answer\n#: Next"
                    question_and_options = self.non_response_question.text%(self.household1.uid, self.household_head.surname) + non_response_option_page
                    non_response_question = "responseString=%s&action=request" % question_and_options
                    self.assertEquals(urllib2.unquote(response.content), non_response_question)

    def test_paginates_households_non_response_questions_options(self):
        household_member = self.create_household_member(name="bob son", household=self.household1, head=False, date_of_birth="1996-9-9")
        self.batch.activate_non_response_for(self.kampala)
        QuestionOption.objects.create(question=self.non_response_question, text="Reason 5", order=5)
        QuestionOption.objects.create(question=self.non_response_question, text="Reason 6", order=6)
        QuestionOption.objects.create(question=self.non_response_question, text="Reason 7", order=7)
        QuestionOption.objects.create(question=self.non_response_question, text="Reason 8", order=8)
        with patch.object(RandomHouseHoldSelection.objects, 'filter', return_value=[1]):
            with patch.object(Survey, "currently_open_survey", return_value=self.open_survey):
                with patch.object(USSDSurvey, 'is_active', return_value=False):
                    self.reset_session()
                    self.report_non_response()
                    response = self.select_household()
                    non_response_option_page_1 = "\n1: House closed\n2: Household moved\n3: Refused to answer\n#: Next"
                    question_and_options_page_1 = self.non_response_question.text%(self.household1.uid, self.household_head.surname) + non_response_option_page_1
                    non_response_question_page_1 = "responseString=%s&action=request" % question_and_options_page_1
                    self.assertEquals(urllib2.unquote(response.content), non_response_question_page_1)

                    response = self.respond("#")
                    non_response_option_page_2 = "\n4: Died\n5: Reason 5\n6: Reason 6\n*: Back\n#: Next"
                    question_and_options_page_2 = self.non_response_question.text%(self.household1.uid, self.household_head.surname) + non_response_option_page_2
                    non_response_question_page_2 = "responseString=%s&action=request" % question_and_options_page_2
                    self.assertEquals(urllib2.unquote(response.content), non_response_question_page_2)

                    invalid_option = '456'
                    response = self.respond(invalid_option)
                    invalid_page_2 = "responseString=%s&action=request" % (
                        "INVALID ANSWER: " + question_and_options_page_2)
                    self.assertEquals(urllib2.unquote(response.content), invalid_page_2)

                    invalid_option = 'blabliblofkajf89748u2&^^%%^&*'
                    response = self.respond(invalid_option)
                    invalid_page_2 = "responseString=%s&action=request" % (
                        "INVALID ANSWER: " + question_and_options_page_2)
                    self.assertEquals(urllib2.unquote(response.content), invalid_page_2)

                    response = self.respond("#")
                    non_response_option_page_3 = "\n7: Reason 7\n8: Reason 8\n*: Back"
                    question_and_options_page_3 = self.non_response_question.text%(self.household1.uid, self.household_head.surname) + non_response_option_page_3
                    non_response_question = "responseString=%s&action=request" % question_and_options_page_3
                    self.assertEquals(urllib2.unquote(response.content), non_response_question)

                    response = self.respond("*")
                    self.assertEquals(urllib2.unquote(response.content), non_response_question_page_2)

                    response = self.respond("*")
                    self.assertEquals(urllib2.unquote(response.content), non_response_question_page_1)

    def test_saves_households_non_response_question_answers_and_show_non_complete_household_list_again_with_stars(self):
        household_member = self.create_household_member(name="bob son", household=self.household1, head=False, date_of_birth="1996-9-9")

        self.batch.activate_non_response_for(self.kampala)
        with patch.object(RandomHouseHoldSelection.objects, 'filter', return_value=[1]):
            with patch.object(Survey, "currently_open_survey", return_value=self.open_survey):
                self.reset_session()
                self.report_non_response()
                self.select_household()
                response = self.respond("2")
                household_list = USSD.MESSAGES['HOUSEHOLD_LIST'] + "\n1: Household-%s-%s*\n2: Household-%s" \
                                                                   "\n3: Household-%s\n4: Household-%s" \
                                 % (self.household1.uid, self.household_head.surname,
                                    self.household2.uid, self.household3.uid, self.household4.uid)
                first_page_list = "responseString=%s&action=request" % household_list
                self.assertEquals(urllib2.unquote(response.content), first_page_list)

                self.assertEquals(2, MultiChoiceAnswer.objects.get(investigator=self.investigator, batch=self.batch,
                                                                   question=self.non_response_question,
                                                                   household=self.household1).answer.order)

    def test_shows_household_members_who_did_not_complete_when_household_is_selected(self):
        self.batch.activate_non_response_for(self.kampala)

        household_member = self.create_household_member(name="bob son", household=self.household1, head=False, date_of_birth="1996-9-9")
        household_member_who_completed = self.create_household_member(name="bob good son", household=self.household1, head=False, date_of_birth="1996-9-1")
        household_member_who_completed.batch_completed(self.batch)

        with patch.object(RandomHouseHoldSelection.objects, 'filter', return_value=[1]):
            with patch.object(Survey, "currently_open_survey", return_value=self.open_survey):
                self.reset_session()
                self.report_non_response()
                response = self.select_household()
                households_member_list = (USSD.MESSAGES['MEMBERS_LIST'], self.household_head.surname,
                                          household_member.surname)
                expected_screen = "%s\n1: %s - (HEAD)\n2: %s" % households_member_list
                response_string = "responseString=%s&action=request" % expected_screen
                self.assertEquals(urllib2.unquote(response.content), response_string)

    def test_paginates_list_of_household_members_who_did_not_complete_when_household_is_selected(self):
        household_member_who_completed = self.create_household_member(name="bob good son", household=self.household1, head=False, date_of_birth="1996-9-1")
        household_member_who_completed.batch_completed(self.batch)

        self.batch.activate_non_response_for(self.kampala)

        household_member1 = self.create_household_member(name="bob1", household=self.household1, head=False, date_of_birth="1996-9-9")
        household_member2 = self.create_household_member(name="bob2", household=self.household1, head=False, date_of_birth="1996-9-10")
        household_member3 = self.create_household_member(name="bob3", household=self.household1, head=False, date_of_birth="1996-9-11")
        household_member4 = self.create_household_member(name="bob4", household=self.household1, head=False, date_of_birth="1996-9-12")
        household_member5 = self.create_household_member(name="bob5", household=self.household1, head=False, date_of_birth="1996-9-13")
        household_member6 = self.create_household_member(name="bob6", household=self.household1, head=False, date_of_birth="1996-9-14")
        household_member7 = self.create_household_member(name="bob7", household=self.household1, head=False, date_of_birth="1996-9-15")
        household_member8 = self.create_household_member(name="bob8", household=self.household1, head=False, date_of_birth="1996-9-16")

        with patch.object(RandomHouseHoldSelection.objects, 'filter', return_value=[1]):
            with patch.object(Survey, "currently_open_survey", return_value=self.open_survey):
                self.reset_session()
                self.report_non_response()
                response = self.select_household()
                households_member_list = (USSD.MESSAGES['MEMBERS_LIST'], self.household_head.surname,
                                          household_member1.surname, household_member2.surname, household_member3.surname)
                expected_screen_page_1 = "%s\n1: %s - (HEAD)\n2: %s\n3: %s\n4: %s\n#: Next" % households_member_list
                member_list_page_1 = "responseString=%s&action=request" % expected_screen_page_1
                self.assertEquals(urllib2.unquote(response.content), member_list_page_1)

                response = self.respond("#")
                households_member_list = (USSD.MESSAGES['MEMBERS_LIST'], household_member4.surname, household_member5.surname,
                                          household_member6.surname, household_member7.surname)
                expected_screen_page_2 = "%s\n5: %s\n6: %s\n7: %s\n8: %s\n*: Back\n#: Next" % households_member_list
                member_list_page_2 = "responseString=%s&action=request" % expected_screen_page_2
                self.assertEquals(urllib2.unquote(response.content), member_list_page_2)

                invalid_option = '456'
                response = self.respond(invalid_option)
                invalid_page_2 = "responseString=%s&action=request" % (
                    "INVALID SELECTION: " + expected_screen_page_2)
                self.assertEquals(urllib2.unquote(response.content), invalid_page_2)

                invalid_option = 'blabliblofkajf89748u2&^^%%^&*'
                response = self.respond(invalid_option)
                invalid_page_2 = "responseString=%s&action=request" % (
                    "INVALID SELECTION: " + expected_screen_page_2)
                self.assertEquals(urllib2.unquote(response.content), invalid_page_2)

                response = self.respond("#")
                households_member_list = (USSD.MESSAGES['MEMBERS_LIST'], household_member8.surname)
                expected_screen_page_3 = "%s\n9: %s\n*: Back" % households_member_list
                member_list_page_3 = "responseString=%s&action=request" % expected_screen_page_3
                self.assertEquals(urllib2.unquote(response.content), member_list_page_3)

                response = self.respond("*")
                self.assertEquals(urllib2.unquote(response.content), member_list_page_2)

                response = self.respond("*")
                self.assertEquals(urllib2.unquote(response.content), member_list_page_1)

    def test_should_not_show_household_members_who_completed_when_household_is_selected(self):
        self.batch.activate_non_response_for(self.kampala)

        household_member = self.create_household_member(name="bob son", household=self.household1, head=False, date_of_birth="1996-9-9")
        household_member.batch_completed(self.batch)

        with patch.object(RandomHouseHoldSelection.objects, 'filter', return_value=[1]):
            with patch.object(Survey, "currently_open_survey", return_value=self.open_survey):
                self.reset_session()
                self.report_non_response()
                response = self.select_household()
                households_member_list = (USSD.MESSAGES['MEMBERS_LIST'], self.household_head.surname)
                expected_screen = "%s\n1: %s - (HEAD)" % households_member_list
                response_string = "responseString=%s&action=request" % expected_screen
                self.assertEquals(urllib2.unquote(response.content), response_string)

    def test_should_show_household_members_non_response_question_when_member_is_selected(self):
        self.batch.activate_non_response_for(self.kampala)

        household_member_who_completed = self.create_household_member(name="bob good son", household=self.household1, head=False, date_of_birth="1996-9-1")
        household_member_who_completed.batch_completed(self.batch)

        with patch.object(RandomHouseHoldSelection.objects, 'filter', return_value=[1]):
            with patch.object(Survey, "currently_open_survey", return_value=self.open_survey):
                self.reset_session()
                self.report_non_response()
                self.select_household()
                response = self.select_household_member()
                non_response_option_page = "\n1: Member Refused\n2: Reason"
                question_and_options = self.member_non_response_question.text%self.household_head.surname + non_response_option_page
                non_response_question = "responseString=%s&action=request" % question_and_options
                self.assertEquals(urllib2.unquote(response.content), non_response_question)

    def test_should_paginate_household_members_non_response_question_options(self):
        self.batch.activate_non_response_for(self.kampala)
        household_member_who_completed = self.create_household_member(name="bob good son", household=self.household1, head=False, date_of_birth="1996-9-1")
        household_member_who_completed.batch_completed(self.batch)


        QuestionOption.objects.create(question=self.member_non_response_question, text="Reason 2", order=3)
        QuestionOption.objects.create(question=self.member_non_response_question, text="Reason 3", order=4)
        QuestionOption.objects.create(question=self.member_non_response_question, text="Reason 4", order=5)
        QuestionOption.objects.create(question=self.member_non_response_question, text="Reason 5", order=6)
        QuestionOption.objects.create(question=self.member_non_response_question, text="Reason 6", order=7)
        QuestionOption.objects.create(question=self.member_non_response_question, text="Reason 7", order=8)
        QuestionOption.objects.create(question=self.member_non_response_question, text="Reason 8", order=9)

        with patch.object(RandomHouseHoldSelection.objects, 'filter', return_value=[1]):
            with patch.object(Survey, "currently_open_survey", return_value=self.open_survey):
                self.reset_session()
                self.report_non_response()
                self.select_household()
                response = self.select_household_member()
                non_response_option_page = "\n1: Member Refused\n2: Reason\n3: Reason 2\n#: Next"
                question_and_options = self.member_non_response_question.text%self.household_head.surname + non_response_option_page
                non_response_question_page_1 = "responseString=%s&action=request" % question_and_options
                self.assertEquals(urllib2.unquote(response.content), non_response_question_page_1)

                response = self.respond("#")
                non_response_option_page_2 = "\n4: Reason 3\n5: Reason 4\n6: Reason 5\n*: Back\n#: Next"
                question_and_options_page_2 = self.member_non_response_question.text%self.household_head.surname + non_response_option_page_2
                non_response_question_page_2 = "responseString=%s&action=request" % question_and_options_page_2
                self.assertEquals(urllib2.unquote(response.content), non_response_question_page_2)

                invalid_option = '456'
                response = self.respond(invalid_option)
                invalid_page_2 = "responseString=%s&action=request" % (
                    "INVALID ANSWER: " + question_and_options_page_2)
                self.assertEquals(urllib2.unquote(response.content), invalid_page_2)

                invalid_option = 'blabliblofkajf89748u2&^^%%^&*'
                response = self.respond(invalid_option)
                invalid_page_2 = "responseString=%s&action=request" % (
                    "INVALID ANSWER: " + question_and_options_page_2)
                self.assertEquals(urllib2.unquote(response.content), invalid_page_2)

                response = self.respond("#")
                non_response_option_page_3 = "\n7: Reason 6\n8: Reason 7\n9: Reason 8\n*: Back"
                question_and_options_page_3 = self.member_non_response_question.text%self.household_head.surname + non_response_option_page_3
                non_response_question = "responseString=%s&action=request" % question_and_options_page_3
                self.assertEquals(urllib2.unquote(response.content), non_response_question)

                response = self.respond("*")
                self.assertEquals(urllib2.unquote(response.content), non_response_question_page_2)

                response = self.respond("*")
                self.assertEquals(urllib2.unquote(response.content), non_response_question_page_1)

    def test_saves_households_member_non_response_question_answers_and_shows_the_members_again_with_stars(self):
        household_member = self.create_household_member(name="bob son", household=self.household1, head=False, date_of_birth="1996-9-9")
        household_member_who_completed = self.create_household_member(name="bob good son", household=self.household1, head=False, date_of_birth="1996-9-1")
        household_member_who_completed.batch_completed(self.batch)

        self.batch.activate_non_response_for(self.kampala)
        with patch.object(RandomHouseHoldSelection.objects, 'filter', return_value=[1]):
            with patch.object(Survey, "currently_open_survey", return_value=self.open_survey):
                self.reset_session()
                self.report_non_response()
                self.select_household()
                self.select_household_member()
                response = self.respond("1")

                households_member_list = (USSD.MESSAGES['MEMBERS_LIST'], self.household_head.surname,
                                          household_member.surname)
                expected_screen = "%s\n1: %s - (HEAD)*\n2: %s" % households_member_list
                response_string = "responseString=%s&action=request" % expected_screen
                self.assertEquals(urllib2.unquote(response.content), response_string)

                self.assertEquals(1, MultiChoiceAnswer.objects.get(investigator=self.investigator, batch=self.batch,
                                                                   question=self.member_non_response_question,
                                                                   household=self.household1, householdmember=self.household_head).answer.order)

    def test_should_show_non_response_of_next_member_with_his_name_when_a_member_has_finished_and_next_one_chosen(self):
        household_member = self.create_household_member(name="bob son", household=self.household1, head=False, date_of_birth="1996-9-9")
        household_member_who_completed = self.create_household_member(name="bob good son", household=self.household1, head=False, date_of_birth="1996-9-1")
        household_member_who_completed.batch_completed(self.batch)

        self.batch.activate_non_response_for(self.kampala)
        with patch.object(RandomHouseHoldSelection.objects, 'filter', return_value=[1]):
            with patch.object(Survey, "currently_open_survey", return_value=self.open_survey):
                self.reset_session()
                self.report_non_response()
                self.select_household()
                self.select_household_member()
                self.respond("1")
                response = self.select_household_member("2")
                non_response_option_page = "\n1: Member Refused\n2: Reason"
                question_and_options = self.member_non_response_question.text%household_member.surname + non_response_option_page
                non_response_question = "responseString=%s&action=request" % question_and_options
                self.assertEquals(urllib2.unquote(response.content), non_response_question)

    def test_shows_household_list_after_all_households_members_for_a_household_all_have_finished_and_shows_stars(self):
        household_member = self.create_household_member(name="bob son", household=self.household1, head=False, date_of_birth="1996-9-9")
        household_member_who_completed = self.create_household_member(name="bob good son", household=self.household1, head=False, date_of_birth="1996-9-1")
        household_member_who_completed.batch_completed(self.batch)

        self.batch.activate_non_response_for(self.kampala)
        with patch.object(RandomHouseHoldSelection.objects, 'filter', return_value=[1]):
            with patch.object(Survey, "currently_open_survey", return_value=self.open_survey):
                self.reset_session()
                self.report_non_response()
                self.select_household()
                self.select_household_member()
                self.respond("1")
                self.select_household_member("2")
                response = self.respond("1")

                household_list = USSD.MESSAGES['HOUSEHOLD_LIST'] + "\n1: Household-%s-%s*\n2: Household-%s" \
                                                                   "\n3: Household-%s\n4: Household-%s" \
                                 % (self.household1.uid, self.household_head.surname,
                                    self.household2.uid, self.household3.uid, self.household4.uid)
                first_page_list = "responseString=%s&action=request" % household_list
                self.assertEquals(urllib2.unquote(response.content), first_page_list)

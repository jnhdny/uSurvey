from django.contrib.auth.models import User
from django.test import Client
from mock import patch
from rapidsms.contrib.locations.models import LocationType, Location
from survey.models import Survey, Batch, Investigator, Household
from survey.tests.base_test import BaseTest
from survey.views.survey_completion import is_valid


class TestSurveyCompletion(BaseTest):
    def setUp(self):
        self.client = Client()
        User.objects.create_user(username='useless', email='rajni@kant.com', password='I_Suck')
        raj = self.assign_permission_to(User.objects.create_user('Rajni', 'rajni@kant.com', 'I_Rock'),
                                        'can_view_batches')
        self.assign_permission_to(raj, 'can_add_location_types')
        self.client.login(username='Rajni', password='I_Rock')
        self.country = LocationType.objects.create(name = 'Country', slug = 'country')
        self.city = LocationType.objects.create(name = 'City', slug = 'city')

        self.uganda = Location.objects.create(name='Uganda', type = self.country)
        self.abim = Location.objects.create(name='Abim', tree_parent = self.uganda, type = self.city)
        self.kampala = Location.objects.create(name='Kampala', tree_parent = self.uganda, type = self.city)
        self.kampala_city = Location.objects.create(name='Kampala City', tree_parent = self.kampala, type = self.city)

        investigator_1 = Investigator.objects.create(name='some_inv',mobile_number='123456789',male=True,location=self.kampala)
        investigator_2 = Investigator.objects.create(name='some_inv',mobile_number='123456788',male=True,location=self.kampala_city)

        self.household_1 = Household.objects.create(investigator = investigator_1,location= self.kampala)
        self.household_2 = Household.objects.create(investigator = investigator_2,location= self.kampala_city)
        self.batch = Batch.objects.create()

    def test_should_render_success_status_code_on_GET(self):
        response = self.client.get('/survey_completion/')
        self.assertEqual(response.status_code,200)

    def test_should_render_template(self):
        response = self.client.get('/survey_completion/')
        templates = [template.name for template in response.templates]
        self.assertIn('aggregates/completion_status.html', templates)

    def test_should_render_context_data(self):
        survey = Survey.objects.create()
        batch = Batch.objects.create()
        response = self.client.get('/survey_completion/')
        self.assertIn(survey,response.context['surveys'])
        self.assertIn(batch,response.context['batches'])
        self.assertIn('survey_completion_rates',response.context['action'])
        locations = response.context['locations'].get_widget_data()
        self.assertEquals(len(locations.keys()), 2)
        self.assertEquals(locations.keys()[0], 'country')
        self.assertEquals(len(locations['country']), 1)
        self.assertEquals(locations['country'][0], self.uganda)
        self.assertEquals(len(locations['city']), 0)

    def test_should_validate_params(self):
        self.assertFalse(is_valid({'location':'2', 'batch':'NOT_A_DIGIT'}))
        self.assertFalse(is_valid({'location':'2', 'batch':''}))

    def test_should_render_error_message_if_params_invalid(self):
        response = self.client.get('/survey_completion/', {'location':'2', 'batch':'NOT_A_DIGIT'})
        error_message = 'Please select a valid location and batch.'
        self.assertIn(error_message, str(response))

    def test_should_render_context_data_after_selecting_location_and_batch(self):
        response = self.client.get('/survey_completion/', {'location': str(self.uganda.pk) ,'batch': str(self.batch.pk)})
        self.assertEqual(self.batch, response.context['selected_batch'])

    def test_should_render_location_children_if_location_in_get_params(self):
        response = self.client.get('/survey_completion/', {'location': str(self.uganda.pk) ,'batch': str(self.batch.pk)})
        self.assertIn(self.abim, response.context['total_households'])
        self.assertIn(self.kampala, response.context['total_households'])

    def test_should_render_total_number_of_household_under_child_locations(self):
        response = self.client.get('/survey_completion/', {'location': str(self.uganda.pk), 'batch': str(self.batch.pk)})
        self.assertEqual(0, response.context['total_households'][self.abim])
        self.assertEqual(2, response.context['total_households'][self.kampala])

    def test_should_render_household_completion_percentage_in_child_locations(self):
        self.household_1.batch_completed(self.batch)
        response = self.client.get('/survey_completion/', {'location': str(self.uganda.pk),'batch':str(self.batch.pk)})
        self.assertEqual(0,response.context['completed_households_percent'][self.abim])
        self.assertEqual(50,response.context['completed_households_percent'][self.kampala])

    @patch('survey.views.survey_completion.render_household_details')
    def test_should_call_households_details_if_lowest_level_selected(self,mock_method):
        response = self.client.get('/survey_completion/', {'location': str(self.kampala_city.pk),'batch':str(self.batch.pk)})
        assert mock_method.called

    def test_should_return_household_objects_if_lowest_level_selected(self):
        response = self.client.get('/survey_completion/', {'location': str(self.kampala_city.pk),'batch':str(self.batch.pk)})
        self.assertNotIn(self.household_1, response.context['households'])
        self.assertIn(self.household_2, response.context['households'])
        self.assertEqual(self.kampala_city,response.context['selected_location'])

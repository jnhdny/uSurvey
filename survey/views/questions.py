import json
import re
from django.core.serializers.json import DjangoJSONEncoder
from django.shortcuts import render
from django.contrib import messages

from django.http import HttpResponseRedirect, HttpResponse
from django.contrib.auth.decorators import permission_required
from survey.forms.logic import LogicForm
from survey.forms.question_filter import QuestionFilterForm
from survey.models import AnswerRule, QuestionModule

from survey.models.batch import Batch
from survey.models.question import Question, QuestionOption
from survey.forms.question import QuestionForm


def _set_filter_condition_based_on_group(group_id, filter_condition):
    if group_id and group_id.lower() != 'all':
        filter_condition['group__id'] = group_id
    return filter_condition


def _set_filter_condition_based_on_module(module_id, filter_condition):
    if module_id and module_id.lower() != 'all':
        filter_condition['module__id'] = module_id
    return filter_condition


def _set_filter_condition_based_on_answer_type(answer_type, filter_condition):
    if answer_type and answer_type.lower() != 'all':
        filter_condition['answer_type'] = answer_type
    return filter_condition


def _set_filter_condition_based_on_batch_id(filter_condition, batch_id=None):
    if batch_id:
        filter_condition['batches'] = Batch.objects.get(id=batch_id)
    return filter_condition


def _get_questions_based_on_filter(batch_id, group_id='All', module_id='All', question_type='All'):
    filter_condition = {}
    filter_condition = _set_filter_condition_based_on_batch_id(filter_condition, batch_id)
    filter_condition = _set_filter_condition_based_on_group(group_id, filter_condition)
    filter_condition = _set_filter_condition_based_on_module(module_id, filter_condition)
    filter_condition = _set_filter_condition_based_on_answer_type(question_type, filter_condition)

    return Question.objects.filter(subquestion=False, **filter_condition)


@permission_required('auth.can_view_batches')
def index(request, batch_id):
    batch = None

    if len(batch_id.strip()) != 0:
        batch = Batch.objects.get(id=batch_id)

    question_filter_form = QuestionFilterForm()
    group_id = request.GET.get('groups', None)
    module_id = request.GET.get('modules', None)
    question_type = request.GET.get('question_types', None)

    if request.method == "POST":
        question_filter_form = QuestionFilterForm(data=request.POST)
        group_id = request.POST.get('groups', None)
        module_id = request.POST.get('modules', None)
        question_type = request.POST.get('question_types', None)

    if not batch_id:
        batch_id = request.POST.get('batch_id', None)

    questions = _get_questions_based_on_filter(batch_id, group_id, module_id, question_type)

    if not questions.exists():
        messages.error(request, 'There are no questions associated with this batch yet.')
    all_questions = questions.exclude(subquestion=True)

    question_rules_for_batch = {}

    if batch:
        for question in all_questions:
            question_rules_for_batch[question] = question.rules_for_batch(batch)

    context = {'questions': all_questions, 'request': request, 'batch': batch,
               'question_filter_form': question_filter_form, 'rules_for_batch': question_rules_for_batch}
    return render(request, 'questions/index.html', context)


@permission_required('auth.can_view_batches')
def filter_by_group_and_module(request, batch_id, group_id, module_id):
    if group_id.lower() != 'all' and module_id.lower() != 'all':
        questions = Question.objects.filter(group__id=group_id, module__id=module_id)
    elif group_id.lower() == 'all' and module_id.lower() != 'all':
        questions = Question.objects.filter(module__id=module_id)
    elif group_id.lower() != 'all' and module_id.lower() == 'all':
        questions = Question.objects.filter(group__id=group_id)
    else:
        questions = Question.objects.filter()

    questions_from_batch = Question.objects.filter(batches__id=batch_id)

    questions = questions.exclude(id__in=questions_from_batch).values('id', 'text', 'answer_type').order_by('text')
    json_dump = json.dumps(list(questions), cls=DjangoJSONEncoder)
    return HttpResponse(json_dump, mimetype='application/json')


@permission_required('auth.can_view_batches')
def list_all_questions(request):
    question_filter_form = QuestionFilterForm()
    group_id = None
    module_id = None
    question_type = None
    batch_id = request.GET.get('batch_id', None)

    if request.method == "POST":
        question_filter_form = QuestionFilterForm(data=request.POST)
        group_id = request.POST.get('groups', None)
        module_id = request.POST.get('modules', None)
        question_type = request.POST.get('question_types', None)
        batch_id = request.POST.get('batch_id', None)

    questions = _get_questions_based_on_filter(batch_id, group_id, module_id, question_type)

    context = {'questions': questions, 'request': request, 'question_filter_form': question_filter_form,
               'rules_for_batch': {}}
    return render(request, 'questions/index.html', context)


def _sub_question_hash(sub_question):
    return {'id': str(sub_question.id), 'text': sub_question.text}


def __process_sub_question_form(request, questionform, parent_question, action_performed, batch_id=None):
    if questionform.is_valid():
        redirect_url = '/batches/%s/questions/' % batch_id if batch_id else '/questions/'

        sub_question = questionform.save(commit=False)
        sub_question.subquestion = True
        sub_question.parent = parent_question
        sub_question.group = parent_question.group
        sub_question.save()

        if request.is_ajax():
            return HttpResponse(json.dumps(_sub_question_hash(sub_question)))
        else:
            messages.success(request, 'Sub question successfully %s.' % action_performed)
            return HttpResponseRedirect(redirect_url)
    else:
        messages.error(request, 'Sub question not saved.')


@permission_required('auth.can_view_batches')
def new_subquestion(request, question_id, batch_id=None):
    parent_question = Question.objects.get(pk=question_id)
    questionform = QuestionForm()
    response = None
    if request.method == 'POST':
        questionform = QuestionForm(request.POST, parent_question=parent_question)
        response = __process_sub_question_form(request, questionform, parent_question, 'added', batch_id)
    context = {'questionform': questionform, 'button_label': 'Create', 'id': 'add-sub_question-form',
               'parent_question': parent_question, 'class': 'question-form', 'heading': 'Add SubQuestion'}

    template_name = 'questions/new.html'
    if request.is_ajax():
        template_name = 'questions/_add_question.html'

    return response or render(request, template_name, context)


@permission_required('auth.can_view_batches')
def edit_subquestion(request, question_id, batch_id=None):
    question = Question.objects.get(pk=question_id)
    questionform = QuestionForm(instance=question)
    response = None
    if request.method == 'POST':
        questionform = QuestionForm(request.POST, instance=question)
        response = __process_sub_question_form(request, questionform, question.parent, 'edited', batch_id)
    context = {'questionform': questionform, 'button_label': 'Save', 'id': 'add-sub_question-form',
               'parent_question': question.parent, 'class': 'question-form', 'heading': 'Edit Subquestion'}

    template_name = 'questions/new.html'

    return response or render(request, template_name, context)


def _get_post_values(post_data):
    next_question_key = post_data.get('next_question', None)
    option_key = post_data.get('option', None)
    question_key = post_data.get('validate_with_question', None)
    condition_response = post_data.get('condition', None)
    value_key = post_data.get('value', None)

    save_data = {'action': post_data['action'],
                 'condition': condition_response if condition_response else 'EQUALS_OPTION',
                 'next_question': Question.objects.get(id=next_question_key) if next_question_key else None,
                 'validate_with_option': QuestionOption.objects.get(id=option_key) if option_key else None,
                 'validate_with_question': Question.objects.get(id=question_key) if question_key else None
    }
    if value_key:
        save_data['validate_with_value'] = value_key

    return save_data


def _rule_exists(question, batch, **kwargs):
    return AnswerRule.objects.filter(question=question, batch=batch, **kwargs).count() > 0


@permission_required('auth.can_view_batches')
def add_logic(request, batch_id, question_id):
    question = Question.objects.get(id=question_id)
    batch = Batch.objects.get(id=batch_id)
    logic_form = LogicForm(question=question, batch=batch)
    response = None
    question_rules_for_batch = {}
    question_rules_for_batch[question] = question.rules_for_batch(batch)

    if request.method == "POST":
        logic_form = LogicForm(data=request.POST, question=question, batch=batch)

        if logic_form.is_valid():
            AnswerRule.objects.create(question=question, batch=batch, **_get_post_values(request.POST))
            messages.success(request, 'Logic successfully added.')
            response = HttpResponseRedirect('/batches/%s/questions/' % batch_id)
    context = {'logic_form': logic_form, 'button_label': 'Save', 'question': question,
               'rules_for_batch': question_rules_for_batch,
               'questionform': QuestionForm(parent_question=question),
               'modal_action': '/questions/%s/sub_questions/new/' % question.id,
               'class': 'question-form', 'batch_id': batch_id, 'batch': batch,
               'cancel_url': '/batches/%s/questions/' % batch_id}
    return response or render(request, "questions/logic.html", context)


@permission_required('auth.can_view_batches')
def new(request):
    response, context = _render_question_view(request)
    return response or render(request, 'questions/new.html', context)


@permission_required('auth.can_view_batches')
def edit(request, question_id):
    question = Question.objects.filter(id=question_id)
    if not question:
        messages.error(request, "Question does not exist.")
        return HttpResponseRedirect('/questions/')
    response, context = _render_question_view(request, question[0])
    return response or render(request, 'questions/new.html', context)


@permission_required('auth.can_view_batches')
def delete(request, question_id, batch_id=None):
    question = Question.objects.filter(pk=question_id)
    redirect_url = '/batches/%s/questions/' % batch_id if batch_id else '/questions/'
    if question:
        success_message = "%s successfully deleted."
        messages.success(request, success_message % ("Sub question" if question[0].subquestion else "Question"))
    else:
        messages.error(request, "Question / Subquestion does not exist.")
    question.delete()
    return HttpResponseRedirect(redirect_url)


def _process_question_form(request, options, response, instance=None):
    question_form = QuestionForm(data=request.POST, instance=instance)
    action_str = 'edit' if instance else 'add'
    if question_form.is_valid():
        question_form.save(**request.POST)
        messages.success(request, 'Question successfully %sed.' % action_str)
        response = HttpResponseRedirect('/questions/')
    else:
        messages.error(request, 'Question was not %sed.' % action_str)
        options = dict(request.POST).get('options', None)
    return response, options, question_form


def _render_question_view(request, instance=None):
    question_form = QuestionForm(instance=instance)
    button_label = 'Create'
    options = None
    response = None
    if instance:
        button_label = 'Save'
        options = instance.options.all()
        options = [option.text for option in options] if options else None

    if request.method == 'POST':
        response, options, question_form = _process_question_form(request, options, response, instance)

    context = {'button_label': button_label,
               'id': 'add-question-form',
               'request': request,
               'class': 'question-form',
               'questionform': question_form}

    if options:
        options = filter(lambda text: text.strip(), list(set(options)))
        options = map(lambda option: re.sub("[%s]" % Question.IGNORED_CHARACTERS, '', option), options)
        context['options'] = map(lambda option: re.sub("  ", ' ', option), options)

    return response, context


def _create_question_hash_response(questions):
    questions_to_display = map(lambda question: {'id': str(question.id), 'text': question.text}, questions)
    return HttpResponse(json.dumps(questions_to_display), mimetype='application/json')


def get_questions_for_batch(request, batch_id, question_id):
    batch = Batch.objects.get(id=batch_id)
    questions = batch.questions.filter(subquestion=False).exclude(id=question_id)
    return _create_question_hash_response(questions)


def get_sub_questions_for_question(request, question_id):
    question = Question.objects.get(id=question_id)
    return _create_question_hash_response(question.get_subquestions())


@permission_required('auth.can_view_batches')
def delete_logic(request, batch_id, answer_rule_id):
    rule = AnswerRule.objects.get(id=answer_rule_id)
    rule.delete()
    messages.success(request, "Logic successfully deleted.")
    return HttpResponseRedirect('/batches/%s/questions/' % batch_id)


@permission_required('auth.can_view_batches')
def remove(request, batch_id, question_id):
    batch = Batch.objects.get(id=batch_id)
    question = Question.objects.get(id=question_id, batches__id=batch_id)
    AnswerRule.objects.filter(question=question, batch=batch).delete()
    question.de_associate_from(batch)
    messages.success(request, "Question successfully removed from %s." % batch.name)
    return HttpResponseRedirect('/batches/%s/questions/' % batch_id)
import pytest
from pytest_mock import MockerFixture

from src.generics.tests.clients import PneumaticApiClient
from src.processes.enums import FieldType, TaskStatus
from src.processes.models.templates.fields import (
    FieldTemplate,
    FieldTemplateSelection,
)
from src.processes.models.workflows.fields import TaskField
from src.processes.services.workflow_action import WorkflowActionService

from ...fixtures import (  # noqa: TID252
    create_task_completed_webhook,
    create_test_fieldset_template,
    create_test_owner,
    create_test_template,
    create_test_workflow,
)

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ('output', 'expected_location'),
    [
        ({}, 'https://example.org/meeting'),
        ({'location': ''}, ''),
        ({'location': 'Room 2'}, 'Room 2'),
    ],
)
def test_task_output_defaults(
    api_client: PneumaticApiClient,
    mocker: MockerFixture,
    output: dict[str, str],
    expected_location: str,
) -> None:
    """Start with template defaults and deliver the saved task output."""
    user = create_test_owner()
    create_task_completed_webhook(user)
    send_webhook = mocker.patch(
        'src.processes.services.workflow_action.'
        'send_task_completed_webhook.delay',
    )
    template = create_test_template(user, tasks_count=2, is_active=True)
    task_template = template.tasks.get(number=2)
    FieldTemplate.objects.create(
        account=user.account,
        template=template,
        task=task_template,
        api_name='duration',
        name='Duration',
        type=FieldType.STRING,
        is_hidden=True,
        default='40',
    )
    location = FieldTemplate.objects.create(
        account=user.account,
        template=template,
        task=task_template,
        api_name='location',
        name='Location',
        type=FieldType.STRING,
        default='https://example.org/meeting',
    )
    FieldTemplate.objects.create(
        account=user.account,
        template=template,
        task=task_template,
        api_name='invalid-date',
        name='Invalid date',
        type=FieldType.DATE,
        default='not a timestamp',
    )
    fieldset = create_test_fieldset_template(
        account=user.account,
        template=template,
        task=task_template,
    )
    channels = fieldset.fields.get()
    channels.type = FieldType.CHECKBOX
    channels.default = 'Email, Phone'
    channels.save(update_fields=['type', 'default'])
    for value in ('Email', 'Phone'):
        FieldTemplateSelection.objects.create(
            field_template=channels,
            template=template,
            value=value,
        )

    workflow = create_test_workflow(user, template=template)
    first_task = workflow.tasks.get(number=1)
    task = workflow.tasks.get(number=2)
    assert task.status == TaskStatus.PENDING
    assert task.output.get(api_name='duration').value == ''
    assert task.fieldsets.get().fields.get().value == ''
    location.default = 'Changed after workflow creation'
    location.save(update_fields=['default'])
    api_client.token_authenticate(user)

    response = api_client.post(f'/v2/tasks/{first_task.id}/complete')
    assert response.status_code == 200, response.data

    response = api_client.get(f'/v2/tasks/{task.id}')
    assert response.status_code == 200, response.data
    assert response.data['status'] == TaskStatus.ACTIVE
    fields = {field['api_name']: field for field in response.data['output']}
    assert fields['duration']['is_hidden'] is True
    assert fields['duration']['value'] == '40'
    assert fields['location']['value'] == 'https://example.org/meeting'
    assert fields['invalid-date']['value'] == ''
    grouped_field = response.data['fieldsets'][0]['fields'][0]
    assert grouped_field['value'] == 'Email, Phone'
    assert grouped_field['markdown_value'] == 'Email, Phone'

    send_webhook.reset_mock()
    response = api_client.post(
        f'/v2/tasks/{task.id}/complete',
        {'output': output},
        format='json',
    )
    assert response.status_code == 200, response.data
    assert response.data['status'] == TaskStatus.COMPLETED
    send_webhook.assert_called_once()
    webhook_task = send_webhook.call_args.kwargs['payload']['task']
    webhook_values = {
        field['api_name']: field['value'] for field in webhook_task['output']
    }
    assert webhook_values == {
        'duration': '40',
        'invalid-date': '',
        'location': expected_location,
    }
    assert webhook_task['fieldsets'][0]['fields'][0]['value'] == 'Email, Phone'


def test_resume_task_keeps_cleared_output() -> None:
    """Resuming an active task does not apply its defaults again."""
    user = create_test_owner()
    workflow = create_test_workflow(user, tasks_count=1)
    task = workflow.tasks.get(number=1)
    task.status = TaskStatus.DELAYED
    task.save(update_fields=['status'])
    field = TaskField.objects.create(
        account=user.account,
        workflow=workflow,
        task=task,
        name='Location',
        type=FieldType.STRING,
        template_default='Room 1',
        value='',
    )

    WorkflowActionService(workflow=workflow, user=user).resume_task(task)

    field.refresh_from_db()
    assert task.status == TaskStatus.ACTIVE
    assert field.value == ''

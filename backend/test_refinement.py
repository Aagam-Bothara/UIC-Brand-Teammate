'''Offline unit tests for Task 3.7 refinement handling.'''

import io
import json

import pytest

from backend.services.llm_service import LLMService
from backend.services.refinement import (
    RefinementHandler,
    RefinementValidationError,
    plan_refinement,
)


class FakeBedrockClient:
    def __init__(self):
        self.request = None

    def invoke_model(self, **kwargs):
        self.request = kwargs
        body = {
            'content': [{'text': '[CONTENT]A concise result.[/CONTENT]'}],
            'usage': {'input_tokens': 100, 'output_tokens': 20},
        }
        return {'body': io.BytesIO(json.dumps(body).encode('utf-8'))}


@pytest.mark.parametrize(('request', 'expected'), [
    ('Make it shorter', 'shorten'),
    ('Please expand this with more detail', 'expand'),
    ('Use a more formal voice', 'formal'),
    ('Make this casual and friendly', 'casual'),
    ('Simplify this with plain language', 'simplify'),
    ('Make this welcoming and enthusiastic', 'welcoming'),
    ('Rewrite in active voice', 'active_voice'),
])
def test_common_refinement_patterns_are_recognized(request, expected):
    plan = plan_refinement('The current document.', request)
    assert expected in plan.patterns
    assert plan.instructions
    assert plan.rulesets


def test_multiple_patterns_are_combined_without_duplicate_rulesets():
    plan = plan_refinement(
        'A long and difficult communication.',
        'Make it shorter, simpler, and more welcoming.',
    )
    assert plan.patterns == ('shorten', 'simplify', 'welcoming')
    assert plan.rulesets == (
        'CONTENT', 'ACCESSIBILITY', 'READING_LEVEL', 'AUDIENCE_TONE'
    )


def test_unknown_request_remains_supported_as_custom_instruction():
    plan = plan_refinement(
        'Current text.', 'Mention the application deadline first.'
    )
    assert plan.patterns == ('custom',)
    assert plan.rulesets == ('CONTENT',)


def test_selected_text_prompt_preserves_the_rest_of_the_document():
    text = 'Keep this. Change these words. Keep this too.'
    start = text.index('Change')
    end = start + len('Change these words.')
    handler = RefinementHandler()
    plan = handler.plan(text, 'Make it shorter', start, end)
    prompt = handler.build_prompt(text, plan, 'Students', 'Email', 'Grade 8')
    assert plan.selected_text == 'Change these words.'
    assert '<selected-text>Change these words.</selected-text>' in prompt
    assert 'Return only replacement text for the selected span' in prompt
    assert plan.to_dict()['is_partial'] is True


@pytest.mark.parametrize(
    ('start', 'end'), [(0, None), (-1, 2), (2, 2), (0, 100), (True, 2)]
)
def test_invalid_selections_are_rejected(start, end):
    with pytest.raises(RefinementValidationError):
        plan_refinement('Some text', 'Make it shorter', start, end)


@pytest.mark.parametrize('text,request', [('', 'shorten'), ('text', '  ')])
def test_empty_inputs_are_rejected(text, request):
    with pytest.raises(RefinementValidationError):
        plan_refinement(text, request)


def test_llm_service_uses_plan_and_returns_refinement_metadata():
    client = FakeBedrockClient()
    service = LLMService(bedrock_client=client)
    text = 'Keep this sentence. This sentence is unnecessarily wordy.'
    start = text.index('This sentence')
    response = service.refine_text(
        current_text=text,
        refinement_request='Make it shorter and simpler.',
        audience='Students',
        channel='Website',
        selection_start=start,
        selection_end=len(text),
    )
    request_body = json.loads(client.request['body'])
    prompt = request_body['messages'][0]['content']
    assert response.refinement['patterns'] == ('shorten', 'simplify')
    assert response.refinement['is_partial'] is True
    assert response.text == (
        text[:start] + '[CONTENT]A concise result.[/CONTENT]'
    )
    assert 'Target reading level: Grade 8' in prompt
    assert 'Preserve all existing valid change tags' in prompt
    assert response.selection['metrics']['task'] == 'refinement'

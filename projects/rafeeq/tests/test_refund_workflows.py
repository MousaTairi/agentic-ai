from __future__ import annotations

import json

import pytest
from test_system import ScriptedModel, answer, tool

from rafeeq.agent import run_agent
from rafeeq.config import Settings
from rafeeq.domain import decide, permit_info, verify
from rafeeq.schemas import Verify
from rafeeq.scope import intent
from rafeeq.storage import Store


@pytest.mark.parametrize('config', ['A', 'B'])
@pytest.mark.parametrize('response', [
    answer('أحتاج أولاً إلى التحقق من هويتك. يرجى استخدام نموذج التحقق الآمن.'),
    tool('start_verification', {'permit_id': 'SGN-40388'}),
])
async def test_verified_duplicate_refund_completes_proposal_without_reverification(tmp_path, config, response):
    store = Store(tmp_path)
    sid = store.new_session()
    verify(store, sid, Verify(permit_id='SGN-40388', last4='2277', mobile='0505502277'))
    model = ScriptedModel([response, answer('هل ترغب في المتابعة؟')])
    reply = await run_agent(store, sid, 'دفعت مرتين لطلب SGN-40388. تحقق واقترح طلب استرداد الدفعة المكررة.',
                            Settings(runtime=tmp_path, configuration=config, max_cost=10), model)
    assert reply.stopped == 'completed' and not reply.ui_requests
    assert 'get_permit' in reply.tools and 'request_refund' in reply.tools
    assert reply.tools.index('get_permit') < reply.tools.index('request_refund')
    action = reply.actions[0]
    assert action['status'] == 'pending' and action['result']['amount_sar'] == 500
    with store.connect() as db:
        assert db.execute('SELECT count(*) FROM refunds').fetchone()[0] == 0
    assert decide(store, sid, action['id'], True)['status'] == 'completed'
    with store.connect() as db:
        assert db.execute("SELECT amount_sar FROM refunds WHERE permit_id='SGN-40388'").fetchone()[0] == 500
    assert decide(store, sid, action['id'], True)['status'] == 'completed'
    # Minimized eligibility facts, not account or payment identifiers, enter model context.
    context = json.dumps(model.messages[0])
    assert 'refund_options' in context and 'duplicate_payment' in context
    assert '0505502277' not in context and 'national_id' not in context


@pytest.mark.parametrize('config', ['A', 'B'])
async def test_rejected_refund_reads_record_and_keeps_separate_finance_gate(tmp_path, config):
    store = Store(tmp_path)
    sid = store.new_session()
    verify(store, sid, Verify(permit_id='SGN-40220', last4='0093', mobile='0540410093'))
    model = ScriptedModel([tool('request_refund', {'permit_id': 'SGN-40220', 'reason': 'rejected'})])
    reply = await run_agent(store, sid, 'I want a refund for rejected SGN-40220. Check the record and propose the refund request.',
                            Settings(runtime=tmp_path, configuration=config, max_cost=10), model)
    assert reply.tools.index('get_permit') < reply.tools.index('request_refund')
    assert len(model.messages) == 1 and reply.actions[0]['result']['amount_sar'] == 2700
    assert decide(store, sid, reply.actions[0]['id'], True)['status'] == 'awaiting_officer'
    with store.connect() as db:
        assert db.execute('SELECT count(*) FROM refunds').fetchone()[0] == 0


@pytest.mark.parametrize('state', ['unverified', 'expired', 'different'])
async def test_refund_fallback_cannot_cross_identity_scope(tmp_path, state):
    store = Store(tmp_path)
    sid = store.new_session()
    if state != 'unverified':
        verify(store, sid, Verify(permit_id='SGN-40388', last4='2277', mobile='0505502277'))
    if state == 'expired':
        with store.connect() as db:
            db.execute('UPDATE sessions SET verified_until=0 WHERE id=?', (sid,))
    target = 'SGN-40220' if state == 'different' else 'SGN-40388'
    reply = await run_agent(store, sid, f'I want a duplicate payment refund for {target}.',
                            Settings(runtime=tmp_path, max_cost=10), ScriptedModel([answer('Verify first.')]))
    assert not reply.actions and 'get_permit' not in reply.tools and 'request_refund' not in reply.tools
    assert any(card['type'] == 'verification' and card.get('permit_id') == target for card in reply.ui_requests)


@pytest.mark.parametrize('message', ['What is the refund policy?', 'Can I request a refund for a rejected permit?',
                                    'ما سياسة استرداد رسوم الطلب المرفوض؟', 'هل أستطيع طلب استرداد الدفعة المكررة؟'])
def test_refund_policy_questions_remain_policy(message):
    assert intent(message) == 'policy'


async def test_no_duplicate_payment_means_no_fallback_proposal(tmp_path):
    store = Store(tmp_path)
    sid = store.new_session()
    verify(store, sid, Verify(permit_id='FTR-30311', last4='6654', mobile='0532236654'))
    assert not permit_info(store, sid, 'FTR-30311')['refund_options']
    reply = await run_agent(store, sid, 'I want a duplicate payment refund for FTR-30311.',
                            Settings(runtime=tmp_path, max_cost=10), ScriptedModel([answer('No eligible duplicate payment.')]))
    assert not reply.actions and 'request_refund' not in reply.tools

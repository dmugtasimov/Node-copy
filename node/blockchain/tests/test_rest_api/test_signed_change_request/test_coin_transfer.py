import json
from unittest.mock import MagicMock, patch

import pytest

from node.blockchain.facade import BlockchainFacade
from node.blockchain.inner_models import CoinTransferSignedChangeRequestMessage, SignedChangeRequest
from node.blockchain.inner_models.signed_change_request_message import CoinTransferTransaction
from node.blockchain.models import AccountState
from node.blockchain.tests.base import as_role
from node.blockchain.tests.test_models.base import CREATE, VALID, coin_transfer_message_type_validation_parametrizer
from node.blockchain.types import NodeRole
from node.core.utils.collections import deep_update


@pytest.mark.usefixtures('base_blockchain', 'as_primary_validator')
def test_coin_transfer_signed_change_request_as_primary_validator(
    api_client, treasury_account_key_pair, treasure_coin_transfer_signed_change_request, treasury_amount
):
    facade = BlockchainFacade.get_instance()
    assert facade.get_next_block_number() == 1

    payload = treasure_coin_transfer_signed_change_request.json()
    response = api_client.post('/api/signed-change-requests/', payload, content_type='application/json')
    assert response.status_code == 201
    assert response.json() == {
        'message': {
            'account_lock': '4d3cf1d9e4547d324de2084b568f807ef12045075a7a01b8bec1e7f013fc3732',
            'txs': [{
                'amount': 100,
                'is_fee': False,
                'memo': 'message',
                'recipient': '1c8e5f54a15b63a9f3d540ce505fd0799575ffeaac62ce625c917e6d915ea8bb'
            }, {
                'amount': 5,
                'is_fee': True,
                'memo': 'message',
                'recipient': 'b9dc49411424cce606d27eeaa8d74cb84826d8a1001d17603638b73bdc6077f1'
            }],
            'type': 2
        },
        'signature':
            '16fefa4441a2f877ecc2e08e7055dfc7ad1c9f4357ada4085dba76bbd37f7fd8'
            '77b18eb45f08ef3562d8029e740717c29a352421d7040cc1fae5b80308da2a09',
        'signer': '4d3cf1d9e4547d324de2084b568f807ef12045075a7a01b8bec1e7f013fc3732'
    }

    assert facade.get_next_block_number() == 2
    account_state = AccountState.objects.get_or_none(_id=treasury_account_key_pair.public)
    total_amount = treasure_coin_transfer_signed_change_request.message.get_total_amount()
    assert account_state.balance == treasury_amount - total_amount
    assert account_state.node is None
    assert account_state.pk == treasury_account_key_pair.public


@pytest.mark.django_db
@coin_transfer_message_type_validation_parametrizer
def test_type_validation_for_coin_transfer(
    id_, account_lock, transaction, recipient, is_fee, amount, memo, search_re, expected_response_body, api_client
):
    tx = CoinTransferTransaction(recipient='0' * 64, amount=10, is_fee=True, memo='message')
    payload = {
        'signer': '0' * 64,
        'signature': '0' * 128,
        'message': {
            'type':
                2,
            'account_lock':
                '0' * 64 if account_lock is VALID else account_lock,
            'txs': [
                tx.dict() if transaction is VALID else ({
                    'recipient': tx.recipient if recipient is VALID else recipient,
                    'is_fee': tx.is_fee if is_fee is VALID else is_fee,
                    'amount': tx.amount if amount is VALID else amount,
                    'memo': tx.memo if memo is VALID else memo,
                } if transaction is CREATE else transaction)
            ]
        }
    }
    response = api_client.post('/api/signed-change-requests/', json.dumps(payload), content_type='application/json')
    assert response.status_code == 400
    response_json = response.json()
    response_json.pop('non_field_errors', None)
    assert response_json == expected_response_body


@pytest.mark.parametrize('key', ('signer', 'signature', 'message'))
@pytest.mark.django_db
def test_checking_missed_keys(
    key, api_client, treasury_account_key_pair, treasure_coin_transfer_signed_change_request, treasury_amount
):
    payload = treasure_coin_transfer_signed_change_request.dict()
    del payload[key]
    response = api_client.post('/api/signed-change-requests/', json.dumps(payload), content_type='application/json')
    assert response.status_code == 400
    assert response.json() == {key: [{'message': 'This field is required.', 'code': 'required'}]}


@pytest.mark.usefixtures('base_blockchain', 'as_primary_validator')
def test_coin_transfer_signed_change_request_with_invalid_account_lock(
    api_client, treasury_account_key_pair, regular_node_key_pair
):
    message = CoinTransferSignedChangeRequestMessage(
        txs=[CoinTransferTransaction(recipient=regular_node_key_pair.public, amount=5)],
        account_lock='0' * 64,
    )

    signed_change_request = SignedChangeRequest.create_from_signed_change_request_message(
        message=message,
        signing_key=treasury_account_key_pair.private,
    )

    payload = signed_change_request.dict()

    response = api_client.post('/api/signed-change-requests/', payload)
    assert response.status_code == 400
    assert response.json() == {'non_field_errors': [{'code': 'invalid', 'message': 'Invalid account lock'}]}


@pytest.mark.django_db
@pytest.mark.parametrize('role', (NodeRole.PRIMARY_VALIDATOR, NodeRole.CONFIRMATION_VALIDATOR, NodeRole.REGULAR_NODE))
@pytest.mark.parametrize(
    'update_with', (
        ({
            'signature': '0' * 128
        }),
        ({
            'signer': '0' * 64
        }),
        ({
            'message': {
                'account_lock': '0' * 64
            }
        }),
        ({
            'message': {
                'txs': [CoinTransferTransaction(recipient='0' * 64, amount=5)]
            }
        }),
    )
)
def test_signature_validation_for_coin_transfer(role, update_with, api_client, treasury_account_key_pair):
    message = CoinTransferSignedChangeRequestMessage(
        txs=[CoinTransferTransaction(recipient=treasury_account_key_pair.public, amount=5)],
        account_lock=treasury_account_key_pair.public,
    )
    signed_change_request = SignedChangeRequest.create_from_signed_change_request_message(
        message=message,
        signing_key=treasury_account_key_pair.private,
    )
    payload = deep_update(signed_change_request.dict(), update_with)
    with as_role(role):
        response = api_client.post('/api/signed-change-requests/', payload)

    assert response.status_code == 400
    assert response.json() == {'non_field_errors': [{'code': 'invalid', 'message': 'Invalid signature'}]}


@pytest.mark.parametrize('role', (NodeRole.CONFIRMATION_VALIDATOR, NodeRole.REGULAR_NODE))
@pytest.mark.usefixtures('base_blockchain', 'mock_get_primary_validator')
def test_coin_transfer_scr_as_other_roles(
    api_client, treasure_coin_transfer_signed_change_request, role, treasury_account_key_pair, primary_validator_node
):
    payload = treasure_coin_transfer_signed_change_request.json()

    response = MagicMock()
    response.status_code = 201
    response.content = payload.encode('utf-8')
    response.headers = {'content-type': 'application/json'}

    with as_role(role):
        with patch('node.core.clients.node.NodeClient.send_signed_change_request', return_value=response) as mock:
            response = api_client.post('/api/signed-change-requests/', payload, content_type='application/json')

    mock.assert_called_once_with(primary_validator_node, treasure_coin_transfer_signed_change_request)

    assert response.status_code == 201
    assert response.json() == {
        'message': {
            'account_lock': '4d3cf1d9e4547d324de2084b568f807ef12045075a7a01b8bec1e7f013fc3732',
            'txs': [{
                'amount': 100,
                'is_fee': False,
                'memo': 'message',
                'recipient': '1c8e5f54a15b63a9f3d540ce505fd0799575ffeaac62ce625c917e6d915ea8bb'
            }, {
                'amount': 5,
                'is_fee': True,
                'memo': 'message',
                'recipient': 'b9dc49411424cce606d27eeaa8d74cb84826d8a1001d17603638b73bdc6077f1'
            }],
            'type': 2
        },
        'signature':
            '16fefa4441a2f877ecc2e08e7055dfc7ad1c9f4357ada4085dba76bbd37f7fd8'
            '77b18eb45f08ef3562d8029e740717c29a352421d7040cc1fae5b80308da2a09',
        'signer': '4d3cf1d9e4547d324de2084b568f807ef12045075a7a01b8bec1e7f013fc3732'
    }

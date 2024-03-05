import logging
import os
import pytest
from botocore.stub import Stubber
from urllib.error import HTTPError

import verify_sender as vs

log_level = os.environ.get('LOG_LEVEL', logging.CRITICAL)
logger = logging.getLogger()
logger.setLevel(log_level)
logging.basicConfig(level=log_level)


def get_invalid_event_data():
    return [
        # No Records (validate sender email flow)
        [
            {},
            [
                {
                    'message': 'Unhandled event type',
                    'code': 'ERROR',
                },
            ],
            {'sent_verification_emails': [], 'verified_emails': []},
        ],
        # Invalid Records (validate sender email flow)
        [
            {
                'Records': [
                    {},
                ],
            },
            [
                {
                    'message': 'Record: 0',
                    'code': 'INFO',
                },
                {
                    'message': 'Unknown or missing record type: {}',
                    'code': 'WARNING',
                },
            ],
            {'sent_verification_emails': [], 'verified_emails': []},
        ],
        [
            {
                'Records': [
                    {"eventSource": "foo"},
                ],
            },
            [
                {
                    'message': 'Record: 0',
                    'code': 'INFO',
                },
                {
                    'message': 'Unknown or missing record type: '
                               '{\'eventSource\': \'foo\'}',
                    'code': 'WARNING',
                },
            ],
            {'sent_verification_emails': [], 'verified_emails': []},
        ],
        [
            {
                'Records': [
                    {"eventSource": "aws:s3", "eventName": "foo"},
                ],
            },
            [
                {
                    'message': 'Record: 0',
                    'code': 'INFO',
                },
                {
                    'message': 'Unknown or missing record type: '
                               '{\'eventSource\': \'aws:s3\', '
                               '\'eventName\': \'foo\'}',
                    'code': 'WARNING',
                },
            ],
            {'sent_verification_emails': [], 'verified_emails': []},
        ],
        [
            {
                'Records': [
                    {"eventSource": "foo", "eventName": "ObjectCreated:Put"}
                ],
            },
            [
                {
                    'message': 'Record: 0',
                    'code': 'INFO'
                },
                {
                    'message': 'Unknown or missing record type: '
                               '{\'eventSource\': \'foo\', '
                               '\'eventName\': \'ObjectCreated:Put\'}',
                    'code': 'WARNING'
                },
            ],
            {'sent_verification_emails': [], 'verified_emails': []},
        ],
        [
            {
                'Records': [
                    {"eventSource": "aws:s3", "eventName": "foo"},
                    {"eventSource": "foo", "eventName": "ObjectCreated:Put"}
                ],
            },
            [
                {
                    'message': 'Record: 0',
                    'code': 'INFO'
                },
                {
                    'message': 'Unknown or missing record type: '
                               '{\'eventSource\': \'aws:s3\', '
                               '\'eventName\': \'foo\'}',
                    'code': 'WARNING'
                },
                {
                    'message': 'Record: 1',
                    'code': 'INFO'
                },
                {
                    'message': 'Unknown or missing record type: '
                               '{\'eventSource\': \'foo\', '
                               '\'eventName\': \'ObjectCreated:Put\'}',
                    'code': 'WARNING'
                }
            ],
            {'sent_verification_emails': [], 'verified_emails': []},
        ],
        # Invalid Records (resend email flow)
        [
            {"source": "aws.foo"},
            [
                {
                    'message': 'Unhandled event type',
                    'code': 'ERROR',
                },
            ],
            {'sent_verification_emails': [], 'verified_emails': []},
        ],
    ]


@pytest.mark.parametrize('event,logs,expected', get_invalid_event_data())
def test_invalid_events(caplog, event, logs, expected):
    """ Tests Invalid Events """

    caplog.set_level(logging.DEBUG, logger="verify_sender")

    response = vs.lambda_handler(event, {})

    assert response == expected

    assert len(caplog.records) == len(logs)

    i = 0
    for record in caplog.records:
        assert record.message == logs[i]['message']
        assert record.levelname == logs[i]['code']
        i += 1


def test_missing_verification_link(caplog):
    """ Tests Missing Verification Link from Blob """

    caplog.set_level(logging.DEBUG, logger="verify_sender")

    event = {
        "Records": [
            {
                "eventSource": "aws:s3",
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "bucket": {
                        "name": "foo",
                    },
                    "object": {
                        "key": "bar/baz",
                        "eTag": "bbe2b5ba2b0c98e8c6f8f06c4bafd713",
                    },
                },
            },
        ],
    }

    # Stub
    s3_stub = Stubber(vs.s3)

    class Body:
        def read(self):
            return b"foo"

    s3_stub.add_response(
        'get_object',
        {
            "Body": Body(),
        },
        {
            "Bucket": "foo",
            "Key": "bar/baz",
            "IfMatch": "bbe2b5ba2b0c98e8c6f8f06c4bafd713",
        },
    )

    s3_stub.activate()

    response = vs.lambda_handler(event, {})

    assert response == {'sent_verification_emails': [], 'verified_emails': []}

    print(caplog.records)

    logs = [
        {
            "message": "Record: 0",
            "code": "INFO",
        },
        {
            "message": "No verification link found for record, skipping",
            "code": "WARNING",
        },
    ]

    assert len(caplog.records) == len(logs)

    i = 0
    for record in caplog.records:
        assert record.message == logs[i]['message']
        assert record.levelname == logs[i]['code']

        i += 1

    s3_stub.deactivate()


def test_valid_event_follow_verification_link(caplog, mocker):
    """ Tests Following Verification Link from Blob """

    caplog.set_level(logging.DEBUG, logger="verify_sender")

    event = {
        "Records": [
            {
                "eventSource": "aws:s3",
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "bucket": {
                        "name": "foo",
                    },
                    "object": {
                        "key": "bar/baz",
                        "eTag": "bbe2b5ba2b0c98e8c6f8f06c4bafd713",
                    },
                },
            },
        ],
    }

    # Stub
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, exc_traceback):
            return None

    mocker.patch('urllib.request.urlopen', return_value=Response())

    s3_stub = Stubber(vs.s3)

    class Body:
        def read(self):
            return (b"To: test@example.com\n"
                    b"\n"
                    b"https://email-verification.eu-west-1.amazonaws.com"
                    b"/foo/bar/baz?foo=bar&baz=sticks\n")

    s3_stub.add_response(
        'get_object',
        {
            "Body": Body(),
        },
        {
            "Bucket": "foo",
            "Key": "bar/baz",
            "IfMatch": "bbe2b5ba2b0c98e8c6f8f06c4bafd713",
        },
    )

    s3_stub.activate()

    response = vs.lambda_handler(event, {})

    assert response == {
        'sent_verification_emails': [],
        'verified_emails': ['test@example.com']
    }

    logs = [
        {
            "message": "Record: 0",
            "code": "INFO",
        },
        {
            "message": "Successfully followed verification link from s3 "
                       "e-mail, email 'test@example.com' should now be able "
                       "to send emails",
            "code": "INFO",
        },
    ]

    assert len(caplog.records) == len(logs)

    i = 0
    for record in caplog.records:
        assert record.message == logs[i]['message']
        assert record.levelname == logs[i]['code']

        i += 1

    s3_stub.deactivate()


def test_valid_resend_emails(caplog, mocker):
    """ Tests Sending Verification Emails to unverified senders """

    caplog.set_level(logging.DEBUG, logger="verify_sender")

    event = {
        "id": "cdc73f9d-aea9-11e3-9d5a-835b769c0d9c",
        "detail-type": "Scheduled Event",
        "source": "aws.events",
        "account": "123456789012",
        "time": "1970-01-01T00:00:00Z",
        "region": "eu-west-1",
        "resources": [
            "arn:aws:events:eu-west-1:123456789012:rule/ExampleRule"
        ],
        "detail": {}
    }

    # Sleeping is slow, mock it instead...
    mocker.patch('time.sleep', return_value=None)

    # Stub
    sesv2_stub = Stubber(vs.sesv2)

    sesv2_stub.add_response(
        'list_email_identities',
        {
            'EmailIdentities': [
                {
                    'IdentityName': 'foo.com',
                    'IdentityType': 'DOMAIN',
                    'SendingEnabled': False,
                },
                {
                    'IdentityName': 'test@foo.com',
                    'IdentityType': 'EMAIL_ADDRESS',
                    'SendingEnabled': False,
                },
                {
                    'IdentityName': 'bar@foo.com',
                    'IdentityType': 'EMAIL_ADDRESS',
                    'SendingEnabled': True,
                },
                {
                    'IdentityName': 'bar@foo.com',
                    'IdentityType': 'EMAIL_ADDRESS',
                    'SendingEnabled': False,
                },
            ],
        },
        {},
    )

    sesv2_stub.activate()

    ses_stub = Stubber(vs.ses)

    ses_stub.add_response(
        'verify_email_address',
        {},
        {
            'EmailAddress': 'test@foo.com',
        },
    )

    ses_stub.add_response(
        'verify_email_address',
        {},
        {
            'EmailAddress': 'bar@foo.com',
        },
    )

    ses_stub.activate()

    response = vs.lambda_handler(event, {})

    assert response == {
        'sent_verification_emails': [
            'test@foo.com',
            'bar@foo.com',
        ],
        'verified_emails': []
    }

    logs = [
        {
            'message': 'Verification e-mail sent to: test@foo.com, '
                       'sleeping 1 second...',
            'code': 'INFO',
        },
        {
            'message': 'Verification e-mail sent to: bar@foo.com, '
                       'sleeping 1 second...',
            'code': 'INFO',
        },
    ]

    assert len(caplog.records) == len(logs)

    i = 0
    for record in caplog.records:
        assert record.message == logs[i]['message']
        assert record.levelname == logs[i]['code']

        i += 1

    sesv2_stub.deactivate()
    ses_stub.deactivate()


def test_url_exception(caplog, mocker):
    """ Tests a URL Exception is caught and logged """

    caplog.set_level(logging.DEBUG, logger="verify_sender")

    event = {
        "id": "cdc73f9d-aea9-11e3-9d5a-835b769c0d9c",
        "detail-type": "Scheduled Event",
        "source": "aws.events",
        "account": "123456789012",
        "time": "1970-01-01T00:00:00Z",
        "region": "eu-west-1",
        "resources": [
            "arn:aws:events:eu-west-1:123456789012:rule/ExampleRule"
        ],
        "detail": {}
    }

    mocker.patch(
        'urllib.request.urlopen',
        side_effect=HTTPError(
            'http://google.co.uk',
            500,
            'Internal Server Error',
            {},
            None
        ),
    )

    event = {
        "Records": [
            {
                "eventSource": "aws:s3",
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "bucket": {
                        "name": "foo",
                    },
                    "object": {
                        "key": "bar/baz",
                        "eTag": "bbe2b5ba2b0c98e8c6f8f06c4bafd713",
                    },
                },
            },
        ],
    }

    s3_stub = Stubber(vs.s3)

    class Body:
        def read(self):
            return (b"To: test@example.com\n"
                    b"\n"
                    b"https://email-verification.eu-west-1.amazonaws.com"
                    b"/foo/bar/baz?foo=bar&baz=sticks\n")

    s3_stub.add_response(
        'get_object',
        {
            "Body": Body(),
        },
        {
            "Bucket": "foo",
            "Key": "bar/baz",
            "IfMatch": "bbe2b5ba2b0c98e8c6f8f06c4bafd713",
        },
    )

    s3_stub.activate()

    response = vs.lambda_handler(event, {})

    assert response == {'sent_verification_emails': [], 'verified_emails': []}

    logs = [
        {
            "message": "Record: 0",
            "code": "INFO",
        },
        {
            "message": "HTTP Error 500: Internal Server Error",
            "code": "ERROR",
        },
    ]

    assert len(caplog.records) == len(logs)

    i = 0
    for record in caplog.records:
        assert record.message == logs[i]['message']
        assert record.levelname == logs[i]['code']

        i += 1

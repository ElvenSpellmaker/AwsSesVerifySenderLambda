import boto3
import email
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from email.header import decode_header

REGION = os.getenv('AWS_DEFAULT_REGION', 'eu-west-1')

SENT_VERIFICATION_EMAILS_KEY = 'sent_verification_emails'
VERIFIED_EMAILS_KEY = 'verified_emails'

log_level = os.environ.get('LOG_LEVEL', 'WARNING').upper()
root_logger = logging.getLogger()
root_logger.setLevel(level=log_level)

logger_name = os.path.splitext(os.path.basename(__file__))[0]
logger = logging.getLogger(logger_name)

ses = boto3.client('ses', region_name=REGION)
sesv2 = boto3.client('sesv2', region_name=REGION)
s3 = boto3.client('s3', region_name=REGION)


def lambda_handler(event, context):
    """
        AWS Lambda for verifying sender email identities and will re-send
        verification emails too
        :param event:   Trigger event.
        :param context: Lambda context.
        :return:        Outcome.
    """

    response = {
        SENT_VERIFICATION_EMAILS_KEY: [],
        VERIFIED_EMAILS_KEY: [],
    }

    # Possibly an S3 PutObject trigger
    if 'Records' in event:
        response[VERIFIED_EMAILS_KEY] = process_verification_email(
            event['Records']
        )
        return response

    # Cloudwatch Event trigger
    if 'source' in event and event['source'] == 'aws.events':
        response[SENT_VERIFICATION_EMAILS_KEY] = unverified_email_check()
        return response

    logger.error('Unhandled event type')
    return response


def process_verification_email(records):
    verification_emails = []

    regex = re.compile(
        f'https://email-verification\\.{REGION}\\.amazonaws\\.com/.+'
    )

    i = 0
    for record in records:
        logger.info(f'Record: {i}')
        i += 1
        if ('eventSource' not in record
                or 'eventName' not in record
                or record['eventSource'] != 'aws:s3'
                or record['eventName'] != 'ObjectCreated:Put'):
            logger.warning(f'Unknown or missing record type: {record}')
            continue

        email_object = s3.get_object(
            Bucket=record['s3']['bucket']['name'],
            Key=record['s3']['object']['key'],
            IfMatch=record['s3']['object']['eTag'],
        )

        message = email.message_from_bytes(email_object['Body'].read())

        verification_link = regex.search(message.as_string())

        if verification_link is None:
            logger.warning('No verification link found for record, skipping')
            continue

        verification_link = verification_link.group(0)

        success, recipient = follow_verification_email_link(
            verification_link,
            message
        )

        if success is True:
            verification_emails.append(recipient)

    return verification_emails


def follow_verification_email_link(verification_link, message):
    httprequest = urllib.request.Request(
        verification_link, method='GET'
    )

    try:
        with urllib.request.urlopen(httprequest) as httpresponse:
            if httpresponse.status == 200:
                recipient, _ = decode_header(message['To'])[0]
                logger.info(
                    (
                        'Successfully followed verification link '
                        f'from s3 e-mail, email \'{recipient}\' should '
                        'now be able to send emails'
                    )
                )

                return True, recipient
    except urllib.error.HTTPError as e:
        logger.error(e)
        return False, None


def unverified_email_check():
    sent_emails = []

    identities = sesv2.list_email_identities()

    for identity in identities['EmailIdentities']:
        if (identity['IdentityType'] == 'EMAIL_ADDRESS'
                and identity['SendingEnabled'] is False):
            email = identity['IdentityName']
            send_verification_email(email)
            sent_emails.append(email)

    return sent_emails


def send_verification_email(email):
    ses.verify_email_address(
        EmailAddress=email
    )
    logger.info(f'Verification e-mail sent to: {email}, sleeping 1 second...')
    time.sleep(1)

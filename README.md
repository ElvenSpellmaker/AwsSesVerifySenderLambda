AWS SES Verify Sender Lambda
============================

Verifies Amazon SES E-Mail Addresses in an S3 Bucket.

 - Python 3.9
 - Pipenv

Overview
--------

This lambda function has two current functionalities:
  - Re-Sends a verification e-mail
  - Verifies a verification e-mail by following the link sent to the S3 bucket.

Lambda Invoker
--------------

Location: `/lambda_invoker.py`

E.g.: `make lambda_invoker TARGET=follow_verify_link`

This is a script to call the local Lambda Function using fake events which aids
in testing the Lambda.

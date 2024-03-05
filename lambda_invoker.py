# creating another endpoint into the lambda fn
import json
import os
import sys

import verify_sender

# setting globals

context = type('', (), {})()
context.aws_request_id = '123123123123'


def tester(c):
    choice_map = {
        'send_verification': verify_sender,
        'follow_verify_link': verify_sender,
    }

    function = choice_map.get(sys.argv[1])

    if function is None:
        print('Supplied argument not in choice map', file=sys.stderr)
        os._exit(1)

    e = json.load(
        open(
            os.path.join(sys.path[0], f'_sample_event_{sys.argv[1]}.json'), 'r'
        )
    )

    result = function.lambda_handler(e, c)

    print(f'{result}')
    return


tester(context)

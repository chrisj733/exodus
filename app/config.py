import os
import re

conf = {'DOMAIN' : os.environ['DOMAIN'],
        'MAIL_HOST': os.environ.get('MAIL_HOST', 'mailtrap.unx.sas.com'),
        'MAIL_PORT': int(os.environ.get('MAIL_PORT', '10025')),
        'LICENSE_API': os.environ.get('LICENSE_API', 'https://dplicenseservice.itcf-dev.sas.com/api/v2'),
        'LICENSE_API_TIMEOUT': os.environ.get('LICENSE_API_TIMEOUT', '10'),
        'DP_CLIENT_ID': os.environ.get('DP_CLIENT_ID', None),
        'DP_CLIENT_SECRET': os.environ.get('DP_CLIENT_SECRET', None),
        'DP_AUTH_URL': os.environ.get('DP_AUTH_URL', None),
        'ALLOW_MULTIPLE_TRIALS_PER_USER': os.environ.get('ALLOW_MULTIPLE_TRIALS_PER_USER', '').split(' '),
        'IS_DEVELOPMENT': os.environ.get('IS_DEVELOPMENT', None) == 'true',
        'DP_API_KEY': os.environ.get('DP_API_KEY','').strip()}


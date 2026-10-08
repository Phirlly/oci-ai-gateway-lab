"""Validate journal pagination before constructing another fixed-host request."""

import re
from urllib.parse import parse_qs, urlsplit

from .credential_errors import DeliveryError

TASK = 'gateway_submission'


def next_page(link, repository, repository_id, current):
    if link is None:
        return None
    try:
        if not isinstance(link, str) or not link or len(link) > 8192:
            raise ValueError
        relations = {}
        for part in link.split(','):
            match = re.fullmatch(r'\s*<([^<>]+)>;\s*rel="(next|prev|first|last)"\s*', part)
            if match is None or match[2] in relations:
                raise ValueError
            url = urlsplit(match[1])
            if (url.scheme != 'https' or url.netloc != 'api.github.com' or url.fragment
                    or url.path not in (f'/repos/{repository}/deployments',
                                        f'/repositories/{repository_id}/deployments')):
                raise ValueError
            query = parse_qs(url.query, strict_parsing=True, keep_blank_values=True)
            if (set(query) != {'task', 'per_page', 'page'} or query['task'] != [TASK]
                    or query['per_page'] != ['100'] or len(query['page']) != 1
                    or re.fullmatch('[1-9][0-9]*', query['page'][0]) is None):
                raise ValueError
            relations[match[2]] = int(query['page'][0])
        following = relations.get('next')
        if following is not None and following != current + 1:
            raise ValueError
        if ('first' in relations and relations['first'] != 1
                or 'prev' in relations and relations['prev'] != current - 1):
            raise ValueError
        last = relations.get('last')
        if last is not None and (last < current or (following is None and last != current)
                                 or (following is not None and last < following)):
            raise ValueError
        return following
    except (ValueError, TypeError):
        raise DeliveryError('Journal pagination could not be verified.') from None

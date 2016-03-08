import datetime
import iso8601
import six
import six.moves.urllib.parse as urlparse
from oslo_log import log as logging
from oslo_utils import timeutils

LOG = logging.getLogger(__name__)


class StartGreaterThanEnd(Exception):
    def __init__(self):
        self.msg = ("Invalid start time. The start time cannot occur after "
                    "the end time.")
        super(StartGreaterThanEnd, self).__init__(self.msg)


class InvalidStrTime(Exception):
    def __init__(self, msg):
        super(InvalidStrTime, self).__init__(msg)
        self.msg = msg


def parse_strtime(dstr, fmt):
    try:
        return timeutils.parse_strtime(dstr, fmt)
    except (TypeError, ValueError) as e:
        raise InvalidStrTime(six.text_type(e))


def parse_datetime(dtstr):
    """
    Parse a datetime string.

    :param dtstr: String
    """
    if not dtstr:
        value = timeutils.utcnow()
    elif isinstance(dtstr, datetime.datetime):
        value = dtstr
    else:
        for fmt in ["%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S.%f",
                    "%Y-%m-%d %H:%M:%S.%f"]:
            try:
                value = parse_strtime(dtstr, fmt)
                break
            except InvalidStrTime:
                pass
        else:
            msg = "Datetime is in invalid format"
            raise InvalidStrTime(msg)

        # NOTE(mriedem): Instance object DateTime fields are timezone-aware
        # so we have to force UTC timezone for comparing this datetime against
        # volume object fields and still maintain backwards compatibility
        # in the API.
        if value.utcoffset() is None:
            value = value.replace(tzinfo=iso8601.iso8601.Utc())
        return value


def get_datetime_range(req):
    """Gets the datetime range from a wsgi request.

    :param req: Dict
    :param service: String - one of (nova, glance, cinder)
    """
    query_string = req.environ.get('QUERY_STRING', '')
    env = urlparse.parse_qs(query_string)
    period_start = parse_datetime(env.get('start', [None])[0])
    period_stop = parse_datetime(env.get('end', [None])[0])
    if not period_start < period_stop:
        raise StartGreaterThanEnd()

    detailed = env.get('detailed', ['0'])[0] == '1'
    return (period_start, period_stop, detailed)

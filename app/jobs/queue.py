from redis import Redis
from rq import Queue

from app.core.config import settings

redis_conn = Redis.from_url(settings.redis_url)
queue = Queue(settings.rq_queue, connection=redis_conn)

# OCR на сканах PDF может занимать несколько минут.
PARSE_JOB_TIMEOUT_SEC = 600
MATCH_JOB_TIMEOUT_SEC = 900

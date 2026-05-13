from redis import Redis
from rq import Queue

from app.core.config import settings

redis_conn = Redis.from_url(settings.redis_url)
queue = Queue(settings.rq_queue, connection=redis_conn)

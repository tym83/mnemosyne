"""Scheduling policy independent of Kubernetes and the artistic pipeline."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import hashlib


def window(policy, now, *, idle=False):
    """Return (night identity, remaining seconds), or None. DST uses UTC duration."""
    local = now.astimezone(ZoneInfo(policy.get('timeZone', 'Etc/UTC')))
    mode = policy.get('kind', 'night')
    start, end = policy.get('startHour', 1), policy.get('endHour', 6)
    if mode == 'idle' and not idle:
        return None
    if mode in ('always', 'idle'):
        deadline = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        day = local.date()
    elif mode == 'weekends':
        if local.weekday() < 5:
            return None
        day = local.date()
        deadline = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        if start == end:
            raise ValueError('night window must have different start and end hours')
        if start < end:
            if not start <= local.hour < end:
                return None
            day = local.date()
        else:
            if end <= local.hour < start:
                return None
            day = (local - timedelta(days=1)).date() if local.hour < end else local.date()
        deadline = datetime.combine(day, datetime.min.time(), local.tzinfo).replace(hour=end)
        if start > end:
            deadline += timedelta(days=1)
    return str(day), max(1, int(deadline.timestamp() - now.timestamp()))


def job_name(uid, night):
    return 'mnemo-' + hashlib.sha256(f'{uid}:{night}'.encode()).hexdigest()[:24]

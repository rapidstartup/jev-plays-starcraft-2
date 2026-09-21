"""Jev decisions via OpenRouter Decisions SDK, TypeSafe System One, or OpenJev (Codiv/local)."""
import os
import json
import asyncio
import time
from urllib.parse import urlparse
from openrouter import OpenRouter
from openrouter.errors import BadRequestResponseError
from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy, TypeSafeBadRequestError


class CallBudgetReached(Exception):
    pass


_OPENROUTER_MODELS = {'typesafe/jev-1.13', '~typesafe/jev-latest'}
_TYPESAFE_MODELS = {'jev-1.13.0', 'jev-latest', 'jev-preview'}
_TYPESAFE_MODEL_MAP = {
    'typesafe/jev-1.13': 'jev-1.13.0',
    '~typesafe/jev-latest': 'jev-1.13.0',
}
_OPENJEV_MODELS = {'openjev-latest', 'openjev-0.1'}
_OPENJEV_MODEL_MAP = {
    'openjev': 'openjev-latest',
    'openjev-latest': 'openjev-latest',
    'openjev-0.1': 'openjev-0.1',
}
DEFAULT_OPENJEV_BASE_URL = 'https://api.codiv.ai'
_LOCAL_OPENJEV_HOSTS = frozenset({
    'localhost', '127.0.0.1', '::1', '192.168.0.10',
})


def _resolve_typesafe_model(name):
    mapped = _TYPESAFE_MODEL_MAP.get(name, name)
    if mapped not in _TYPESAFE_MODELS:
        raise ValueError(
            f'This experiment permits Jev only; got {name!r} '
            f'(typesafe models: {sorted(_TYPESAFE_MODELS)})'
        )
    return mapped


def _resolve_openjev_model(name):
    """Map openjev* names; otherwise default to openjev-latest for this via."""
    if not name or not str(name).strip():
        return 'openjev-latest'
    raw = str(name).strip()
    if raw in _OPENJEV_MODEL_MAP:
        return _OPENJEV_MODEL_MAP[raw]
    if raw.startswith('openjev'):
        if raw in _OPENJEV_MODELS:
            return raw
        raise ValueError(
            f'Unknown OpenJev model {raw!r} '
            f'(openjev models: {sorted(_OPENJEV_MODELS)} or aliases openjev)'
        )
    return 'openjev-latest'


def resolve_openjev_base_url():
    """Codiv hosted by default; OPENJEV_BASE_URL / TYPESAFE_BASE_URL override (local later)."""
    for env in ('OPENJEV_BASE_URL', 'TYPESAFE_BASE_URL'):
        value = (os.environ.get(env) or '').strip()
        if value:
            return value.rstrip('/')
    return DEFAULT_OPENJEV_BASE_URL


def openjev_host_only(base_url=None):
    """Hostname (and port if non-default) for control.json — never a key."""
    url = base_url if base_url is not None else resolve_openjev_base_url()
    parsed = urlparse(url if '://' in url else f'https://{url}')
    host = parsed.hostname or url
    if parsed.port:
        return f'{host}:{parsed.port}'
    return host


def openjev_via_label(base_url=None):
    host = (openjev_host_only(base_url) or '').lower()
    # Strip port for local-host check
    host_name = host.split(':')[0]
    if host_name in _LOCAL_OPENJEV_HOSTS or host_name.startswith('192.168.'):
        return 'openjev_local'
    return 'openjev_codiv'


def _normalize_via(raw):
    via = (raw or 'openrouter').strip().lower()
    if via in ('', 'openrouter'):
        return 'openrouter'
    if via == 'typesafe':
        return 'typesafe'
    if via in ('openjev', 'codiv'):
        return 'openjev'
    raise ValueError(
        f'JEV_VIA must be openrouter, typesafe, openjev, or codiv; got {via!r}'
    )


def _openjev_api_key():
    return (
        (os.environ.get('CODIV_API_KEY') or '').strip()
        or (os.environ.get('OPENJEV_API_KEY') or '').strip()
        or (os.environ.get('TYPESAFE_API_KEY') or '').strip()
        or None
    )


class Jev:
    def __init__(self, log, session, max_calls=None):
        via = _normalize_via(os.environ.get('JEV_VIA'))
        self.via = via
        self.timeout_ms = int(os.getenv('JEV_TIMEOUT_MS', '5000'))
        self.log, self.session = log, session
        self.calls = 0
        self.inflight = 0
        # 0 / None / negative => unlimited (no CallBudgetReached)
        self.max_calls = max_calls if max_calls is not None and max_calls > 0 else None
        self.cost = 0.0
        raw_model = os.getenv('JEV_MODEL', 'typesafe/jev-1.13')
        self.base_url = None

        if via == 'typesafe':
            key = os.environ.get('JEV_API_KEY') or os.environ.get('TYPESAFE_API_KEY')
            if not key:
                raise RuntimeError('Set JEV_API_KEY or TYPESAFE_API_KEY for JEV_VIA=typesafe')
            self.api_key = key
            self.model = _resolve_typesafe_model(raw_model)
            self.via_label = 'typesafe_systemone'
            self.client = None  # created per ask with async with
        elif via == 'openjev':
            key = _openjev_api_key()
            if not key:
                raise RuntimeError(
                    'Set CODIV_API_KEY or OPENJEV_API_KEY or TYPESAFE_API_KEY for JEV_VIA=openjev'
                )
            self.api_key = key
            self.base_url = resolve_openjev_base_url()
            self.model = _resolve_openjev_model(raw_model)
            self.via_label = openjev_via_label(self.base_url)
            self.client = None
        else:
            key = os.environ.get('OPENROUTER_API_KEY')
            if not key:
                raise RuntimeError('Set OPENROUTER_API_KEY in .env')
            if raw_model not in _OPENROUTER_MODELS:
                raise ValueError('This experiment permits Jev only')
            self.model = raw_model
            self.api_key = None
            self.via_label = 'openrouter_decisions'
            self.client = OpenRouter(
                api_key=key, x_open_router_title='Jev StarCraft Lab'
            )

        init_fields = {
            'model': self.model,
            'timeout_ms': self.timeout_ms,
            'via': self.via_label,
        }
        if self.base_url:
            init_fields['base_url_host'] = openjev_host_only(self.base_url)
        self.log('jev_init', **init_fields)

    async def ask(self, state, questions):
        # Concrete-order question names exactly identify job summaries. Reapply
        # projection after every recursive split, retaining all other world facts.
        facts = state.get('selection_facts', {})
        if questions and set(questions) <= set(facts) and set(facts) != set(questions):
            state = {**state, 'selection_facts': {key: facts[key] for key in questions}}
        # Conservative transport-size heuristic, not a token-count guarantee.
        # Preserve every question/criterion and the identical fair state.
        if len(questions) > 1 and len(json.dumps([state, questions])) > 80000:
            items = list(questions.items())
            middle = len(items) // 2
            self.log(
                'jev_request_split',
                questions=len(items),
                request_chars=len(json.dumps([state, questions])),
            )
            halves = await asyncio.gather(
                self.ask(state, dict(items[:middle])),
                self.ask(state, dict(items[middle:])),
            )
            return {key: value for half in halves for key, value in half.items()}
        if self.max_calls is not None and self.max_calls > 0 and self.calls + self.inflight >= self.max_calls:
            raise CallBudgetReached()
        self.inflight += 1
        try:
            started = time.monotonic()
            if self.via in ('typesafe', 'openjev'):
                result = await self._ask_systemone(state, questions)
            else:
                result = await self._ask_openrouter(state, questions)
            self.log(
                'jev',
                latency_ms=round((time.monotonic() - started) * 1000),
                timeout_ms=self.timeout_ms,
                via=self.via_label,
                state=state,
                questions=questions,
                response=result,
            )
            return result['answers']
        except (BadRequestResponseError, TypeSafeBadRequestError) as exc:
            self.log(
                'jev_request_rejected',
                request_chars=len(json.dumps([state, questions])),
                state_chars=len(json.dumps(state)),
                question_count=len(questions),
                question_chars={k: len(json.dumps(v)) for k, v in questions.items()},
                detail=str(exc)[:200],
            )
            if 'max_tokens_exceeded' not in str(exc) or len(questions) <= 1:
                raise
            # The server is authoritative about token limits. Splitting a rejected
            # batch retains the exact state, choices and criteria for each question.
            # Release this reservation before children reserve their own requests.
            self.inflight -= 1
            try:
                items = list(questions.items())
                middle = len(items) // 2
                self.log(
                    'jev_request_split',
                    questions=len(items),
                    reason='server_token_limit',
                )
                halves = await asyncio.gather(
                    self.ask(state, dict(items[:middle])),
                    self.ask(state, dict(items[middle:])),
                )
                return {key: value for half in halves for key, value in half.items()}
            finally:
                self.inflight += 1
        finally:
            self.inflight -= 1

    async def _ask_openrouter(self, state, questions):
        response = await self.client.alpha.decisions.create_async(
            model=self.model,
            state=state,
            questions=questions,
            session_id=self.session,
            timeout_ms=self.timeout_ms,
            retries=None,
            # SDK 1.1.158 otherwise appends /api/alpha to /api/v1 (404).
            server_url='https://openrouter.ai',
        )
        self.calls += 1
        self.cost += response.usage.cost or 0
        return response.model_dump(mode='json')

    async def _ask_systemone(self, state, questions):
        """TypeSafe System One path — also used for OpenJev (Codiv or local)."""
        kwargs = {
            'api_key': self.api_key,
            'timeout': self.timeout_ms / 1000.0,
            'retry': RetryPolicy(max_retries=0),
        }
        if self.base_url:
            # Explicit ctor base_url (TYPESAFE_BASE_URL env also works per SDK).
            kwargs['base_url'] = self.base_url
        async with AsyncTypeSafeClient(**kwargs) as client:
            result = await client.system_one(
                state=state, questions=questions, model=self.model
            )
        self.calls += 1
        dumped = result.model_dump()
        usage = dumped.get('usage') if isinstance(dumped, dict) else None
        if isinstance(usage, dict) and usage.get('cost') is not None:
            self.cost += usage['cost']
        # else: no cost field — leave cost unchanged (increment 0); don't crash
        return dumped

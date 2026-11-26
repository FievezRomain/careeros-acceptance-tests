"""Isolated HTTP fixtures using the real service composition with synthetic boundaries."""

import os
import socket
import sys
from itertools import count
from types import SimpleNamespace
from uuid import UUID

import uvicorn


def gateway():
    import httpx
    from careeros_ai_gateway.adapters.discovery import OpenAIQueryExpander, TavilySearch
    from careeros_ai_gateway.adapters.http import Settings, create_app
    from careeros_ai_gateway.application.capability import AccountContext
    from careeros_ai_gateway.application.discovery import DiscoverJobLinks

    calls = count()
    time = count(step=301)

    def search(request):
        resolved = next(calls) >= 2
        protected = 'https://www.linkedin.com/jobs/view/123456'
        independent = 'https://example.invalid/jobs/102'
        snippet = ('Public record https://boards.greenhouse.io/synthetic/jobs/101'
                   if resolved else 'Partial source wording')
        hits = [(protected, snippet), (protected + '?utm_source=fixture', snippet),
                (independent, 'Second role with the same title'), ('http://invalid.example/', 'discard')]
        return httpx.Response(200, json={'results': [
            {'url': url, 'title': 'Platform Engineer', 'content': content, 'score': 0.7}
            for url, content in hits
        ]})

    class Model:
        def parse(self, **kwargs):
            return SimpleNamespace(model='fixture-model', status='completed',
                                   output_parsed={'queries': ['platform engineer paris jobs']})

    class Verifier:
        def verify(self, token):
            if token != 'fixture-gateway':
                raise ValueError('invalid fixture token')
            return AccountContext(account_id=UUID(int=5), tenant_id=UUID(int=6), scopes=('ai:invoke',))

    settings = Settings(app_env='test', log_level='error', oidc_issuer='https://id.example.invalid',
                        oidc_audience='careeros-api')
    retrieval = TavilySearch(httpx.Client(transport=httpx.MockTransport(search)), 'fixture', lambda: next(time))
    return create_app(settings, token_verifier=Verifier(),
                      discovery_gateway=DiscoverJobLinks(OpenAIQueryExpander(Model(), 'fixture'), retrieval))


def jobs():
    import httpx2
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    from careeros_job.adapters.http import create_http_app
    from careeros_job.adapters.postgresql.discovery import SqlAlchemyDiscoveryRepository
    from careeros_job.adapters.postgresql.repository import Base, SqlAlchemyOpportunityRepository
    from careeros_job.adapters.sources.open_web import DiscoverySources, OpenWebGateway
    from careeros_job.application.discovery import RunDailyDiscovery, SynchronizeSearchSnapshot
    from careeros_job.application.manual_capture import (
        AccountContext, CaptureManualOpportunity, QueryOpportunityCatalog, TokenValidationError,
    )
    from careeros_job.application.startup import MigrationState, StartService
    from careeros_job.bootstrap import SystemClock, Uuid4Factory

    class MigrationFixture:
        def apply_pending(self):
            return MigrationState(expected=('fixture',), applied=('fixture',))

        inspect = apply_pending

    class Verifier:
        def verify(self, token):
            actors = {'fixture-owner': ('1', ('jobs:read',)), 'fixture-other': ('3', ('jobs:read',)),
                      'fixture-discovery': ('4', ('discovery:write', 'discovery:run'))}
            if token not in actors:
                raise TokenValidationError
            suffix, scopes = actors[token]
            return AccountContext(account_id=UUID(f'00000000-0000-4000-8000-00000000000{suffix}'),
                                  tenant_id=UUID('00000000-0000-4000-8000-000000000002'), scopes=scopes)

    class Transport(httpx2.HTTPTransport):
        def handle_request(self, request):
            if request.url.host == 'boards-api.greenhouse.io':
                return httpx2.Response(200, json={'id': 101, 'title': 'Platform Engineer',
                                                 'company_name': 'Synthetic Labs', 'content': 'Full description.'})
            return super().handle_request(request)

    engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    repository = SqlAlchemyDiscoveryRepository(engine)
    catalog = SqlAlchemyOpportunityRepository(engine)
    identifiers = Uuid4Factory()
    client = httpx2.Client(transport=Transport())
    source = OpenWebGateway(client, os.environ['FIXTURE_AI_GATEWAY_URL'], 'fixture-gateway')
    sources = DiscoverySources((), source, source)
    return create_http_app(StartService(MigrationFixture()),
        capture_manual=CaptureManualOpportunity(catalog, SystemClock(), identifiers),
        query_catalog=QueryOpportunityCatalog(catalog), token_verifier=Verifier(),
        synchronize_search=SynchronizeSearchSnapshot(repository),
        run_discovery=RunDailyDiscovery(repository, sources, sources, identifiers), shutdown=engine.dispose)


factory = {'gateway': gateway, 'jobs': jobs}[sys.argv[1]]
server = uvicorn.Server(uvicorn.Config(factory(), log_level='warning', access_log=False))
with socket.socket() as listener:
    listener.bind(('127.0.0.1', 0))
    print(f'fixture-port={listener.getsockname()[1]}', flush=True)
    server.run(sockets=[listener])

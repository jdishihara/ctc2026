"""Read retained closed-247 traces and write accounting/design evidence only.

Does not import a strategy/evaluator, simulate a policy, or access the network.
"""
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT=Path('/Users/arjunhans/Documents/ctc2026')
SOURCE=ROOT/'.worktrees/supervised-forward'
PRIOR=ROOT/'out/capture-247-independent-review-20261024'
OUT=Path(__file__).resolve().parent
CID='fd1ebff9-0f96-4533-b283-bc0a5c60cd4b'
forbidden=[]
def guard(event,args):
    if event in ('socket.connect','socket.getaddrinfo','socket.bind'):
        forbidden.append(event);raise RuntimeError('network forbidden')
    if event=='open' and isinstance(args[0],(str,bytes)):
        p=str(args[0]).lower()
        if any(x in p for x in ['/data/history/','.botkey','/.env','credentials','manifest']):
            forbidden.append(p);raise RuntimeError('restricted read forbidden')
sys.addaudithook(guard)
def load(p):return json.loads(p.read_text())
def lines(p):return [json.loads(x) for x in p.read_text().splitlines()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def gz(p):
    with gzip.open(p,'rt') as f:return json.load(f)
def save(name,data):(OUT/name).write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')

inputs={}
def bind(p):inputs[str(p)]=sha(p);return p
archive=bind(PRIOR.with_suffix('.tar.gz'))
assert sha(archive)=='8930064de48813f53025be67a6d0db6e00019e86631b36b6e176d38dc9329b93'
cache=load(bind(PRIOR/'247.json'))
assert sha(PRIOR/'247.json')=='905e7bf98dbd13c913340a9a1999d49a00b6cd6a9209602e089fe20f88d3698e'
receipt=cache['receipt'];assert receipt['competition_id']==CID
assert receipt['clock']['state']==receipt['end_clock']['state']=='ready'
assert receipt['at']==1792835136.260472
epoch=cache['frames'][0]['received_at']
cases=[]
for setting in ['0.0-1.0-0','0.0-0.5-0','0.0-0.5-1']:
    p=PRIOR/'original/supervised'/('capture-247-'+setting)
    r=load(bind(p/'result.json'));events=lines(bind(p/'actions.jsonl'));status=load(bind(p/'status.json'))
    assert r['cleanup_started_at']==2167.5 and r['cleanup_completed_at']==2172.5
    assert r['cleanup']['state']=='attention' and r['cleanup']['reason']=='cleanup retry limit'
    assert {s:q for s,q in r['final_positions'].items() if q}=={'REIN':-6}
    assert not r['server_orders_after_final_receipt'] and r['fills_after_final_receipt_requests']==0
    assert not status['ownership_blocks']
    cleanup=[e for e in events if e['at']>=epoch+r['cleanup_started_at']]
    recent=[e for e in events if epoch+r['cleanup_completed_at']-60<=e['at']<=epoch+r['cleanup_completed_at']]
    mutations=[e for e in recent if e['kind'] in ['request','cleanup_cancel','cleanup_order']]
    assert all(e.get('response') is not None for e in mutations if e['kind']=='request')
    assert all(e['response']=={'cancelled':True} for e in mutations if e['kind']=='cleanup_cancel')
    assert all(e['order_id'] is not None for e in mutations if e['kind']=='cleanup_order')
    assert all(e.get('symbol')!='REIN' for e in cleanup if e['kind']=='cleanup_order')
    cases.append({'setting':setting,'cleanup_start':r['cleanup_started_at'],
        'cleanup_end':r['cleanup_completed_at'],'residual':{'REIN':-6},'open_orders':[],
        'last_60_seconds_observed_mutations':len(mutations),
        'cleanup_posts':sum(e['kind']=='cleanup_order' for e in cleanup),
        'cleanup_deletes':sum(e['kind']=='cleanup_cancel' for e in cleanup),
        'rein_book_requests':r['request_counts']['GET /orderbook/REIN?depth=1'],
        'rein_cleanup_orders':0,'observed_cleanup_rejections':0,
        'receipt_pnl':r['final_receipt']['pnl'],'terminal_pnl':r['terminal_settlement_pnl'],
        'evidence_level':'complete original journals plus shared recorded quote path'})

q=[f for f in cache['frames'] if f['type']=='quote' and f['symbol']=='REIN']
last=max((f for f in q if f['received_at']<epoch+2167.5),key=lambda f:f['received_at'])
nxt=min((f for f in q if f['received_at']>epoch+2172.5),key=lambda f:f['received_at'])
assert last['ask']==nxt['ask']==90.16 and last['ask_size']==20 and nxt['ask_size']==19
assert not any(epoch+2167.5<=f['received_at']<=epoch+2172.5 for f in q)
quote={'last_before_cleanup':last,'next_after_cleanup':nxt,
    'last_relative':last['received_at']-epoch,'next_relative':nxt['received_at']-epoch,
    'quote_age_at_cleanup_entry':epoch+2167.5-last['received_at'],
    'next_quote_after_cleanup_end_seconds':nxt['received_at']-(epoch+2172.5),
    'next_ask_full_units':19,'next_ask_half_units':9,'replay_freshness_seconds':5,
    'interpretation':'Freshness expiration excludes the recorded book; no evidence REIN depth was consumed.'}

trace_cases=[]
for setting in ['0.0-0.5-0','0.05-0.5-0']:
    p=PRIOR/'rerun-supervised'/setting
    r=load(bind(p/'result.json'));requests=gz(bind(p/'request-trace.json.gz'));fills=gz(bind(p/'fill-trace.json.gz'))
    cleanup=[x for x in requests if x['started_at']>=r['cleanup_started_at']]
    rein_books=[{k:x[k] for k in ['started_at','executed_at','completed_at','response']}
                for x in cleanup if x['path']=='/orderbook/REIN?depth=1']
    rein_orders=[{k:x[k] for k in ['started_at','executed_at','completed_at','body','response']}
                for x in cleanup if x['method']=='POST' and x['path']=='/orders' and x['body']['symbol']=='REIN']
    rein_fills=[x for x in fills if x['symbol']=='REIN' and x['t']>=r['cleanup_started_at']]
    assert not any('error' in x for x in requests)
    assert not any(x.get('response') is None for x in requests if x['method']!='GET')
    trace_cases.append({'setting':setting,'cleanup_start':r['cleanup_started_at'],
        'cleanup_end':r['cleanup_completed_at'],'cleanup_state':r['cleanup']['state'],
        'rein_books':rein_books,'rein_orders':rein_orders,'rein_fills':rein_fills,
        'request_errors':0,'mutation_none_responses':0})
assert not trace_cases[0]['rein_orders'] and not trace_cases[0]['rein_fills']
assert all(x['response']=={'bids':[],'asks':[]} for x in trace_cases[0]['rein_books'])
assert sum(x['qty'] for x in trace_cases[1]['rein_fills'])==6

sources={str(bind(SOURCE/p)):sha(SOURCE/p) for p in ['bot/practice.py','bot/live.py',
    'scripts/replay_practice_supervisor.py','scripts/replay_serialized_client.py',
    'scripts/replay_captured_market.py','ctc/sim.py']}
design={
    'decision':'Approved for a predeclared offline implementation/test only with the monotonic extra-pass mutation guard specified here; no production approval.',
    'runtime_changes_implemented':False,'new_policy_simulations_run':0,
    'clock':'practice.time.monotonic (the existing patched clock in frozen replay)',
    'time_origin':'cleanup entry immediately before constructing CleanupExchange',
    'total_pass_cap':62,'unconditional_initial_passes':5,
    'extra_pass_admission':'pass number 6..62 may begin only if elapsed is finite, nonnegative and <=61 seconds; clock regression disables extras',
    'preserve':'All existing requests, gates, ordering, one-second sleeps, acknowledgements, prices and early exits during the first five passes; no new budget gate before pass six.',
    'duration_claim':'Bounds additional pass starts and total passes, not total wall time; an admitted pass, in-flight HTTP, final reconciliation and receipt may finish later.',
    'budget_limit':90,'budget_window_seconds':60,'budget_eviction':'expire only when monotonic age >60; equality still counts',
    'budget_source':'Private monotonic shadow ledger observing existing Journal.event calls from journal creation. Do not reconstruct runtime ages from persisted wall-clock at fields.',
    'count_once':['request with method POST or DELETE, including ETF POSTs and None/rejection responses',
        'cleanup_cancel, including None responses',
        'cleanup_order, including None IDs as a conservative charge'],
    'do_not_count':['request_attempt (paired diagnostic, already represented by request)',
        'GET requests, status, cleanup_attention/flat/settled and extra-pass budget-wait diagnostics'],
    'count_identity':'Conservatively include all counted events in this run, regardless of CID; cleanup ownership fencing remains separate.',
    'extra_mutation_gate':'Before each extra-pass direct DELETE and before each extra-pass place(), require fewer than90 unexpired entries. Synchronous single-owner execution prevents an intervening mutation. Charge the existing completion event at monotonic completion, including rejected or uncertain outcomes.',
    'budget_denial':'Do not call send/place and do not fabricate a None acknowledgement. Defer mutations, retain live orders, reconcile/read only, then sleep/retry within bounds. Do not emit a counted cleanup_order/cancel for a locally deferred action.',
    'uncertainty':'Invalid/missing ledger, malformed event schema, unresolved POST request_attempt, clock failure/regression, or event-write failure disables additional mutations. Existing ownership/lost-ACK guards still terminate; an exception must never resume extra mutation processing.',
    'post_ack_registration':'Keep acknowledged ID registration before status-only-fill refresh.',
    'scope_limit':'The new guard does not retroactively repair first-five-pass budget behavior, account-wide activity outside this journal, or missing live quote data.',
    'required_tests':['first-five-pass request/fill trace equality including existing early exits',
        'quote refresh after old fifth pass and no refresh before new bounds',
        '89 permits one mutation;90 defers POST and DELETE; age60 still counted, age>60 expires',
        'POST/conversion request_attempt+request counted once, direct cleanup DELETE counted, None outcomes charged',
        'wall-clock jump does not age ledger; patched monotonic progression and pass62 cap',
        'budget deferral does not create lost-ACK/ownership block or replace live orders',
        'partial fills, cancel-racing fills, lost ACK, foreign history, CID rollover and market close preserve existing gates',
        'slow first five passes beyond61 produce no extras; admitted final pass may finish after61',
        'complete predeclared evaluation grid, with all losses, residuals, attention states and mutation counts reported']}
report={'diagnosis':'Recorded quote freshness expires and five zero-RTT cleanup passes end before the next REIN quote; no observed action-budget exhaustion.',
    'competition_id':CID,'capture':247,'frozen_driver_revision':'c5c35a30e0c5f521f12324eec854f405b681b8c0',
    'runtime_revision':'cd3eb239bd7bad97b34f10a8f2bb0b2e1c0f5026','cases':cases,'quote_timing':quote,
    'full_trace_cases':trace_cases,'proposal':design,'source_sha256':sources,'input_sha256':inputs,
    'limitations':['Only half-depth/off has a retained full request/fill trace among the three original attention cases; all three have complete original journals and the common recorded quote stream.',
        'Recorded quote freshness is a replay rule, not proof of live REST book emptiness or consumed liquidity.',
        'Next recorded size suffices arithmetically but no extended policy or counterfactual fill/P&L was simulated.',
        'Sixty-one seconds is a structural budget-window bound with one-second polling, not an empirically necessary duration.',
        'Higher RTT permits more elapsed time but changes requests, fills and prices; it is not a causal P&L ablation.'],
    'forbidden_attempts':forbidden}
assert not forbidden and all(sha(Path(p))==h for p,h in inputs.items())
save('diagnosis.json',report)
receipt_out={'schema_version':1,'kind':'diagnosis_artifact_hash_receipt',
    'source_archive_sha256':sha(archive),'new_policy_simulations':0,'strategy_or_runtime_changes':False,
    'artifacts_sha256':{name:sha(OUT/name) for name in ['diagnosis.md','diagnosis.json','build_evidence.py']},
    'input_sha256':inputs,'forbidden_attempts':forbidden}
save('hash-receipt.json',receipt_out)
print(json.dumps({'cases':len(cases),'new_policy_simulations':0,'receipt_sha256':sha(OUT/'hash-receipt.json'),
    'artifacts_sha256':receipt_out['artifacts_sha256']}))

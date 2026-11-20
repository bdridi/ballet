/* Maquettes de la Scène : données et rendus partagés par les trois propositions.
   Les Rehearsals terminées, leurs issues et le Workshop « consume-a-stock-item » viennent d'antimurphy (.ballet/run/,
   19-20 novembre) ; ce qui est « en direct » (FEAT-006.2, TASK-004, BUG-002) est simulé pour montrer la page vivante. */

const NOW = '2026-11-20T21:12:00Z';
const PROJECT = {
  name: 'antimurphy',
  cast: {dramaturg: ['claude', 'opus'], choreographer: ['claude', 'opus'], dancer: ['claude', 'sonnet'], critic: ['claude', 'opus']},
  limits: {max_round_trips: 2, max_diff_lines: 700, max_exchange_rounds: 3},
};
const ROLE_NAMES = {dramaturg: 'Dramaturg', choreographer: 'Choreographer', dancer: 'Dancer', critic: 'Critic', conductor: 'Conductor', director: 'Director', script: 'Script'};

/* --- les features et leurs slices ------------------------------------------------------------------ */

const FEATURES = [
  {id: 'FEAT-001', issue: 1, cap: 'CAP-001 · Stock', title: 'View your stock', mode: 'assisted', workshop: null, planning: null},
  {id: 'FEAT-002', issue: 20, cap: 'CAP-001 · Stock', title: 'Filter your stock', mode: 'autopilot', workshop: null, planning: 'FEAT-002'},
  {id: 'FEAT-003', issue: 13, cap: 'CAP-001 · Stock', title: 'Page through your stock', mode: 'autopilot', workshop: null, planning: null},
  {id: 'FEAT-004', issue: 32, cap: 'CAP-001 · Stock', title: 'Add a stock item by hand', mode: 'assisted', workshop: null, planning: 'FEAT-004'},
  {id: 'FEAT-005', issue: 50, cap: 'CAP-002 · Products', title: 'Create a product', mode: 'autopilot', workshop: null, planning: null},
  {id: 'FEAT-006', issue: 55, cap: 'CAP-001 · Stock', title: 'Consume a stock item', mode: 'assisted', workshop: 'consume-a-stock-item', planning: 'FEAT-006'},
];

// id, issue, titre, PR, statut, allers-retours, lignes du diff, mutations, début, fin
const R = (id, issue, title, pr, status, rt, size, mut, start, end, extra = {}) =>
  ({id, issue, title, pr, status, rt, size, mut, start, end, feature: id.split('.')[0], ...extra});
const REHEARSALS = [
  R('FEAT-001.1', 2, 'Walking skeleton', 8, 'done', 0, 1210, 0, '2026-11-16T10:41Z', '2026-11-16T12:30Z'),
  R('FEAT-001.2', 3, 'Inventory model', 9, 'done', 0, 980, 0, '2026-11-16T12:34Z', '2026-11-16T13:34Z', {director: 'size escalation accepted'}),
  R('FEAT-001.3', 4, 'Stock API', 10, 'done', 0, 1615, 0, '2026-11-16T14:07Z', '2026-11-16T16:17Z'),
  R('FEAT-001.4', 5, 'Stock table', 11, 'done', 1, 897, 0, '2026-11-16T16:21Z', '2026-11-16T16:51Z'),
  R('FEAT-001.5', 6, 'Empty and unavailable stock', 12, 'done', 0, 405, 0, '2026-11-16T17:34Z', '2026-11-16T17:57Z'),
  R('FEAT-002', 20, 'Planification de FEAT-002', null, 'done', 0, 0, 0, '2026-11-16T20:59Z', '2026-11-16T22:53Z', {planning: true}),
  R('FEAT-002.1', 21, 'Filter the stock by status, kit and category in the API', 26, 'done', 0, 579, 0, '2026-11-16T22:53Z', '2026-11-17T06:28Z'),
  R('FEAT-002.2', 22, 'Product search and filter options in the API', 27, 'done', 1, 493, 0, '2026-11-17T06:28Z', '2026-11-17T06:45Z'),
  R('FEAT-002.3', 23, 'Filter controls and the filtered stock client', 28, 'done', 0, 303, 0, '2026-11-17T06:45Z', '2026-11-17T06:58Z'),
  R('FEAT-002.4', 24, 'Filter the stock on screen', 29, 'done', 0, 470, 0, '2026-11-17T06:58Z', '2026-11-17T18:25Z'),
  R('FEAT-002.5', 25, 'Combined filters, no result, back to page 1', 30, 'done', 0, 270, 0, '2026-11-17T18:25Z', '2026-11-17T18:36Z'),
  R('FEAT-003.1', 14, 'Paged stock API', 17, 'done', 0, 408, 0, '2026-11-16T21:12Z', '2026-11-16T21:24Z'),
  R('FEAT-003.2', 15, 'Page 1 with its total', 18, 'done', 0, 232, 0, '2026-11-16T21:24Z', '2026-11-16T21:37Z'),
  R('FEAT-003.3', 16, 'Moving between pages', 19, 'done', 0, 277, 0, '2026-11-16T21:37Z', '2026-11-16T22:31Z'),
  R('FEAT-004', 32, 'Planification de FEAT-004', null, 'done', 0, 0, 0, '2026-11-19T16:37Z', '2026-11-19T16:51Z', {planning: true, director: 'plan approved'}),
  R('FEAT-004.1', 33, 'Kit::add, measures and saving one stock item down to D1', 41, 'done', 0, 867, 2, '2026-11-19T16:51Z', '2026-11-19T17:51Z'),
  R('FEAT-004.2', 34, 'AddStockItem use case', 42, 'done', 0, 812, 2, '2026-11-19T17:51Z', '2026-11-19T18:15Z'),
  R('FEAT-004.3', 35, 'POST /api/stock-items', 43, 'done', 0, 666, 2, '2026-11-19T18:15Z', '2026-11-19T18:34Z'),
  R('FEAT-004.4', 36, "Entry options API and the front's API client", 44, 'done', 0, 814, 2, '2026-11-19T18:34Z', '2026-11-19T18:54Z'),
  R('FEAT-004.5', 37, 'The « Ajouter un lot » screen opens and cancels', 45, 'done', 1, 774, 2, '2026-11-19T18:54Z', '2026-11-19T19:14Z'),
  R('FEAT-004.6', 38, 'Add or merge from the screen', 46, 'done', 1, 762, 2, '2026-11-19T19:14Z', '2026-11-19T19:41Z'),
  R('FEAT-004.7', 39, 'Optional details and refusal messages', 47, 'done', 1, 654, 3, '2026-11-19T19:41Z', '2026-11-19T20:08Z'),
  R('FEAT-004.8', 40, 'Saving fails, then retries', 48, 'done', 0, 239, 2, '2026-11-19T20:30Z', '2026-11-19T20:45Z'),
  R('FEAT-005', 50, 'Create a product', 51, 'done', 0, 2874, 2, '2026-11-19T21:39Z', '2026-11-19T22:35Z', {director: 'size escalation accepted'}),
  R('FEAT-006', 55, 'Planification de FEAT-006', null, 'done', 0, 0, 0, '2026-11-20T20:12Z', '2026-11-20T20:24Z', {planning: true}),
  R('FEAT-006.1', 57, 'The « Consommer » screen and its API', 60, 'done', 0, 512, 2, '2026-11-20T20:24Z', '2026-11-20T20:44Z'),
  R('FEAT-006.2', 58, 'FEFO consumes the earliest expiry first', 61, 'open', 1, 431, 2, '2026-11-20T20:44Z', null, {session: '#55'}),
  R('FEAT-006.3', 59, 'Tie-break and refusal messages', null, 'next', 0, 0, 0, null, null, {session: '#55'}),
  R('TASK-004', 56, 'Cache cargo-mutants in CI', 62, 'escalated', 2, 188, 0, '2026-11-20T20:31Z', null,
    {feature: 'TASK-004', kind: 'Task', session: '#56', escalation: 'proof red 3 times (max_round_trips 2): the cargo-mutants cache key misses on CI'}),
];
const rehearsal = id => REHEARSALS.find(r => r.id === id);
const sliceOf = f => REHEARSALS.filter(r => r.feature === f.id && !r.planning);
const featureOf = id => FEATURES.find(f => f.id === id);

/* --- les sessions de Conductor (une par élément confié) ------------------------------------------- */

const SESSIONS = [
  {kind: 'rehearsal', item: '#55', title: 'FEAT-006 · Consume a stock item', mode: 'assisted', current: 'FEAT-006.2',
    played: ['FEAT-006', 'FEAT-006.1', 'FEAT-006.2'], next: ['FEAT-006.3'], opened: '2026-11-20T20:12Z'},
  {kind: 'rehearsal', item: '#56', title: 'TASK-004 · Cache cargo-mutants in CI', mode: 'autopilot', current: 'TASK-004',
    played: ['TASK-004'], next: [], opened: '2026-11-20T20:31Z', escalated: true},
  {kind: 'workshop', item: 'BUG-002', title: 'Expired items still counted in the kit total', mode: 'autopilot', current: 'BUG-002',
    played: [], next: [], opened: '2026-11-20T21:04Z'},
];

const WORKSHOPS = [
  {id: 'BUG-002', title: 'Expired items still counted in the kit total', mode: 'autopilot', status: 'open', start: '2026-11-20T21:04Z', end: null,
    picked: true, rounds: 1, decided_alone: null, issue: null},
  {id: 'consume-a-stock-item', title: 'Consume a stock item', mode: 'autopilot', status: 'done', start: '2026-11-20T19:52Z', end: '2026-11-20T19:55Z',
    picked: false, request: 'Consume a stock item', rounds: 1, decided_alone: 11, exchanges: 2, issue: 55, pr: 54, published: 'FEAT-006', status_out: 'proposed',
    decisions: ['Merged into the Next up line « CAP-001 Consume a stock item », numbered FEAT-006',
      'Entry point: a « − Consommer » button next to « + Ajouter » on Stock, its own screen (kit → product → quantity)',
      'Consumption is per kit: the same product in another kit is untouched',
      'FEFO ignores unit sizes: a 500 g and a 1 kg packet each count as one unit',
      'Tie-break at equal deadlines: the stock item with the fewest units goes first']},
  {id: 'FEAT-005', title: 'Create a product', mode: 'assisted', status: 'done', start: '2026-11-19T21:10Z', end: '2026-11-19T21:35Z', untracked: true, issue: 50},
  {id: 'FEAT-004', title: 'Add a stock item by hand', mode: 'assisted', status: 'done', start: '2026-11-19T15:40Z', end: '2026-11-19T16:30Z', untracked: true, issue: 32},
];
const workshop = id => WORKSHOPS.find(w => w.id === id);

/* --- le programme (GitHub) ----------------------------------------------------------------------- */

const PROGRAM = {
  ready: [
    {item: '#60', id: 'BUG-001', type: 'Bug', priority: 'P1', mode: 'autopilot', title: 'The quantity field accepts 0', created: '2026-11-20T09:12Z', estimate: 25},
    {item: '#62', id: 'FEAT-007', type: 'Feature', priority: 'P2', mode: 'assisted', title: 'Expiry alerts on the home screen', created: '2026-11-20T11:40Z', estimate: 140, plan: 'required'},
    {item: '#61', id: 'TASK-005', type: 'Task', priority: 'P3', mode: 'autopilot', title: 'Upgrade wrangler to v4', created: '2026-11-20T10:05Z', estimate: 20},
  ],
  proposed: [
    {item: '#63', id: 'FEAT-008', type: 'Feature', title: 'Move a stock item between kits', decided_alone: 4, from: 'Workshop autopilot · 18:20', created: '2026-11-20T18:24Z'},
  ],
  nextUp: [
    {id: 'BUG-002', kind: 'Bug', title: 'Expired items still counted in the kit total', state: 'in workshop'},
    {id: 'OPP-004', kind: 'Opportunity', title: 'Know what to buy before a trip', state: ''},
    {id: 'CAP-003', kind: 'Capability', title: 'Share a kit with the family', state: ''},
  ],
};

/* --- le journal ---------------------------------------------------------------------------------- */

const ev = (at, event, detail = {}) => ({at, event, detail});
const JOURNAL = {
  'FEAT-006.2': [
    ev('2026-11-20T20:44:10Z', 'begin', {item: '#58', plan: 'review', session: '#55'}),
    ev('2026-11-20T20:44:16Z', 'handoff', {role: 'dancer', how: 'start', agent: 'claude', model: 'sonnet', text: 'Play the dancer section of #58: tasks 1-4, red → green → refactor, one commit per task.'}),
    ev('2026-11-20T20:44:16Z', 'wait', {done: ['worktree rehearsal-FEAT-006-2 created from main', 'dancer started (claude sonnet)']}),
    ev('2026-11-20T20:58:40Z', 'message', {from: 'dancer', to: 'conductor', type: 'report', round: 1, text: '- Tasks: 4/4 done, 4 commits\n- Red seen: consume_takes_earliest_expiry fails before FefoPicker\n- Proof: green locally (cargo test, vitest)'}),
    ev('2026-11-20T20:58:41Z', 'policy', {role: 'dancer', violations: []}),
    ev('2026-11-20T20:58:42Z', 'proof-start', {head: '8c1f2e0'}),
    ev('2026-11-20T20:59:44Z', 'proof-end', {passed: true, seconds: 62}),
    ev('2026-11-20T20:59:45Z', 'mutation-start', {tool: 'rust', files: 9, ranges: 31}),
    ev('2026-11-20T21:00:51Z', 'mutation-end', {tool: 'rust', passed: false, seconds: 66, details: '14 killed, 2 survived: fefo.rs:41 (< → <=), fefo.rs:58 (delete !)'}),
    ev('2026-11-20T21:00:52Z', 'wait', {done: ['mutation red: rust (14 killed, 2 survived)', 'survivors sent to the dancer']}),
    ev('2026-11-20T21:00:52Z', 'handoff', {role: 'dancer', how: 'send', text: 'Two mutants survived: fefo.rs:41 (< → <=) and fefo.rs:58 (delete !). Kill each with a unit test.'}),
    ev('2026-11-20T21:09:30Z', 'message', {from: 'dancer', to: 'conductor', type: 'report', round: 2, text: '- 2 tests added: equal_deadlines_keep_order, refuses_empty_kit\n- Proof: green locally'}),
    ev('2026-11-20T21:09:31Z', 'policy', {role: 'dancer', violations: []}),
    ev('2026-11-20T21:09:31Z', 'proof-start', {head: 'b07d3aa'}),
    ev('2026-11-20T21:10:35Z', 'proof-end', {passed: true, seconds: 64}),
    ev('2026-11-20T21:10:36Z', 'mutation-start', {tool: 'rust', files: 9, ranges: 33}),
  ],
  'TASK-004': [
    ev('2026-11-20T20:31:02Z', 'begin', {item: '#56', plan: 'auto', session: '#56'}),
    ev('2026-11-20T20:31:08Z', 'handoff', {role: 'dancer', how: 'start', agent: 'claude', model: 'sonnet', text: 'Play #56.'}),
    ev('2026-11-20T20:40:10Z', 'message', {from: 'dancer', to: 'conductor', type: 'report', round: 1, text: '- CI caches ~/.cargo and target/mutants'}),
    ev('2026-11-20T20:40:11Z', 'policy', {role: 'dancer', violations: []}),
    ev('2026-11-20T20:40:12Z', 'proof-start', {}), ev('2026-11-20T20:41:20Z', 'proof-end', {passed: false, seconds: 68}),
    ev('2026-11-20T20:41:21Z', 'handoff', {role: 'dancer', how: 'send', text: 'Proof red: act job fails, cache key not found.'}),
    ev('2026-11-20T20:49:40Z', 'message', {from: 'dancer', to: 'conductor', type: 'report', round: 2, text: '- Cache key now hashes Cargo.lock'}),
    ev('2026-11-20T20:49:41Z', 'policy', {role: 'dancer', violations: []}),
    ev('2026-11-20T20:49:42Z', 'proof-start', {}), ev('2026-11-20T20:50:51Z', 'proof-end', {passed: false, seconds: 69}),
    ev('2026-11-20T20:50:52Z', 'handoff', {role: 'dancer', how: 'send', text: 'Proof red again.'}),
    ev('2026-11-20T21:00:30Z', 'message', {from: 'dancer', to: 'conductor', type: 'question', round: 3, text: 'Should the proof run act at all? It needs Docker, absent in the worktree.'}),
    ev('2026-11-20T21:00:31Z', 'proof-start', {}), ev('2026-11-20T21:01:40Z', 'proof-end', {passed: false, seconds: 69}),
    ev('2026-11-20T21:02:05Z', 'escalate', {reason: 'proof red 3 times (max_round_trips 2): the cargo-mutants cache key misses on CI', done: ['Ballet status escalated on #56', 'question posted on #56']}),
  ],
  'BUG-002': [
    ev('2026-11-20T21:04:02Z', 'begin', {item: 'BUG-002', picked: true, request: ''}),
    ev('2026-11-20T21:04:06Z', 'handoff', {role: 'dramaturg', how: 'start', agent: 'claude', model: 'opus', text: 'Frame BUG-002 from the backlog, autopilot: decide alone within your scope, record each decision.'}),
    ev('2026-11-20T21:04:06Z', 'wait', {done: ['worktree workshop-BUG-002 created', 'dramaturg started']}),
    ev('2026-11-20T21:07:10Z', 'message', {from: 'dramaturg', to: 'choreographer', type: 'question', round: 1, text: 'Is the kit total computed in the API or on screen? If both, which one is the source of truth?'}),
    ev('2026-11-20T21:07:14Z', 'handoff', {role: 'choreographer', how: 'start', agent: 'claude', model: 'opus', text: 'The dramaturg asks your technical advice (round 1/3).'}),
  ],
  'consume-a-stock-item': [
    ev('2026-11-20T19:52:02Z', 'begin', {item: 'consume-a-stock-item', picked: false, request: 'Consume a stock item'}),
    ev('2026-11-20T19:52:06Z', 'handoff', {role: 'dramaturg', how: 'start', agent: 'claude', model: 'opus', text: 'Frame the request « Consume a stock item », autopilot.'}),
    ev('2026-11-20T19:53:20Z', 'message', {from: 'dramaturg', to: 'choreographer', type: 'question', round: 1, text: 'Does FEFO need the unit size of each stock item, or can each packet count as one unit?'}),
    ev('2026-11-20T19:53:24Z', 'handoff', {role: 'choreographer', how: 'start', agent: 'claude', model: 'opus', text: 'The dramaturg asks your technical advice (round 1/3).'}),
    ev('2026-11-20T19:54:18Z', 'message', {from: 'choreographer', to: 'dramaturg', type: 'answer', round: 1, text: 'No technical constraint: one packet = one unit is enough; unit sizes can come later without migration.'}),
    ev('2026-11-20T19:54:18Z', 'policy', {role: 'choreographer', violations: []}),
    ev('2026-11-20T19:54:20Z', 'handoff', {role: 'dramaturg', how: 'send', text: 'The choreographer answered.'}),
    ev('2026-11-20T19:55:00Z', 'message', {from: 'dramaturg', to: 'conductor', type: 'report', round: 1, text: '- Item: FEAT-006\n- Type: Feature\n- Decided alone: 11 points'}),
    ev('2026-11-20T19:55:01Z', 'policy', {role: 'dramaturg', violations: []}),
    ev('2026-11-20T19:55:18Z', 'published', {item: 'FEAT-006', issue: 55, type: 'Feature', status: 'proposed', decided_alone: 11, exchanges: 2}),
    ev('2026-11-20T19:55:29Z', 'done', {reason: 'issue #55 published as proposed', done: ['workshop/consume-a-stock-item pushed', 'pull request #54 opened', '#54 merged by rebase', 'issue #55 published as Feature, proposed', 'issue #55 marked ballet:decided-alone']}),
  ],
};

/* Une Rehearsal terminée sans journal embarqué : un fil plausible, tiré de ses chiffres (allers-retours, mutations). */
function synthesized(r) {
  if (!r.start) return [];
  const steps = [['begin', {item: '#' + r.issue, plan: 'review'}, 0]];
  if (r.planning) {
    steps.push(['handoff', {role: 'choreographer', how: 'start', agent: 'claude', model: 'opus', text: `Plan ${r.feature}.`}, 0.2],
      ['message', {from: 'choreographer', to: 'conductor', type: 'report', round: 1, text: '- Plan written on the issue\n- Slices created'}, 10],
      ['policy', {role: 'choreographer', violations: []}, 0.1]);
    if (r.director) steps.push(['director-decision', {verdict: 'approve', plan: true}, 3]);
    steps.push(['handover', {to: r.feature + '.1'}, 0.2], ['done', {reason: `planned: its worktree plays ${r.feature}.1`}, 0.1]);
  } else {
    for (let round = 1; round <= r.rt + 1; round++) {
      const last = round === r.rt + 1;
      steps.push(['handoff', {role: 'dancer', how: round === 1 ? 'start' : 'send', agent: 'claude', model: 'sonnet', text: round === 1 ? `Play #${r.issue}.` : 'Blocking points from the critic.'}, 0.2],
        ['message', {from: 'dancer', to: 'conductor', type: 'report', round, text: `- Report round ${round}`}, round === 1 ? 10 : 4],
        ['policy', {role: 'dancer', violations: []}, 0.05], ['proof-start', {}, 0.05], ['proof-end', {passed: true, seconds: 62}, 1]);
      if (r.mut) steps.push(['mutation-start', {tool: 'rust'}, 0.05], ['mutation-end', {tool: 'rust', passed: true, seconds: 65}, 1]);
      steps.push(['diff-size', {counted: r.size, limit: PROJECT.limits.max_diff_lines, over: r.size > PROJECT.limits.max_diff_lines}, 0.1]);
      if (r.size > PROJECT.limits.max_diff_lines && r.director && last) {
        steps.push(['escalate', {reason: `diff ${r.size} lines over ${PROJECT.limits.max_diff_lines}`}, 0.1], ['director-decision', {verdict: 'accept size'}, 3]);
      }
      steps.push(['handoff', {role: 'critic', how: round === 1 ? 'start' : 'send', agent: 'claude', model: 'opus', text: 'Review the branch.'}, 0.1],
        ['message', {from: 'critic', to: 'conductor', type: 'verdict', round, verdict: last ? 'APPROVED' : 'REJECTED', text: last ? 'APPROVED' : 'REJECTED: 2 blocking points'}, 2]);
    }
    steps.push(['done', {reason: `#${r.pr} merged on main`, done: [`verdict APPROVED published on #${r.pr}`, `#${r.pr} merged`, 'worktree removed']}, 0.3]);
  }
  const total = steps.reduce((s, x) => s + x[2], 0), from = +new Date(r.start), span = +new Date(r.end) - from;
  let at = 0;
  return steps.map(([event, detail, weight]) => { at += weight; return ev(new Date(from + span * at / total).toISOString(), event, detail); });
}
const eventsOf = id => JOURNAL[id] || synthesized(rehearsal(id) || {});

/* --- outils ------------------------------------------------------------------------------------- */

const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const clock = at => new Date(at).toLocaleTimeString('fr-FR', {hour: '2-digit', minute: '2-digit', timeZone: 'UTC'});
const dayOf = at => new Date(at).toLocaleDateString('fr-FR', {weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC'});
const minutes = (a, b = NOW) => Math.max(0, Math.round((new Date(b) - new Date(a)) / 60000));
const dur = m => m < 60 ? `${m} min` : m < 2880 ? `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, '0')}` : `${Math.round(m / 1440)} j`;
const ago = at => `il y a ${dur(minutes(at))}`;
const role = who => `<span class="role r-${esc(who)}">${esc(ROLE_NAMES[who] || who)}</span>`;
const STATUS = {open: 'en cours', escalated: 'escaladée', done: 'terminée', next: 'à venir'};
const pill = status => `<span class="pill p-${esc(status)}">${esc(STATUS[status] || status)}</span>`;

/* Le rôle ou l'étape qui a la main dans un fil (null quand rien ne joue). */
function activeStep(events) {
  const last = [...events].reverse().find(e => !['wait', 'policy'].includes(e.event));
  if (!last) return null;
  if (last.event === 'proof-start') return {node: 'proof', kind: 'script', label: 'Preuve en cours', since: last.at};
  if (last.event === 'mutation-start') return {node: 'mutation', kind: 'script', label: 'Mutation en cours', since: last.at};
  if (last.event === 'handoff') return {node: last.detail.role, kind: 'agent', label: `${ROLE_NAMES[last.detail.role]} joue`, since: last.at};
  if (last.event === 'escalate') return {node: 'director', kind: 'human', label: 'Director attendu', since: last.at};
  if (last.event === 'done') return null;
  return {node: 'conductor', kind: 'script', label: 'Script', since: last.at};
}

/* --- le diagramme d'états : agents (pilules), étapes du script (rectangles), Director (losange) --- */

const GRAPHS = {
  rehearsal: {
    w: 1080, h: 250,
    nodes: {
      begin: [50, 105, 'script', 'Ouverture', 'worktree + branche'],
      plan: [165, 105, 'agent', 'Choreographer', 'plan + slices', 'choreographer'],
      dancer: [295, 105, 'agent', 'Dancer', 'red → green', 'dancer'],
      policy: [420, 105, 'script', 'Politique', 'périmètre'],
      proof: [530, 105, 'script', 'Preuve', 'tests du repo'],
      mutation: [640, 105, 'script', 'Mutation', 'en arrière-plan'],
      size: [750, 105, 'script', 'Taille', 'max_diff_lines'],
      critic: [870, 105, 'agent', 'Critic', 'verdict', 'critic'],
      premiere: [1010, 105, 'script', 'Premiere', 'merge sur main'],
      director: [640, 215, 'human', 'Director', 'escalade / tampon', 'director'],
    },
    edges: [['begin', 'plan'], ['plan', 'dancer'], ['begin', 'dancer', 'skip'], ['dancer', 'policy'], ['policy', 'proof'], ['proof', 'mutation'],
      ['mutation', 'size'], ['size', 'critic'], ['critic', 'premiere'], ['proof', 'dancer', 'back'], ['mutation', 'dancer', 'back'], ['critic', 'dancer', 'back'],
      ['proof', 'director', 'esc'], ['size', 'director', 'esc'], ['critic', 'director', 'esc'], ['plan', 'director', 'esc'], ['director', 'premiere', 'esc']],
  },
  workshop: {
    w: 1080, h: 250,
    nodes: {
      begin: [60, 90, 'script', 'Ouverture', 'ligne du backlog'],
      dramaturg: [240, 90, 'agent', 'Dramaturg', 'cadre la feature', 'dramaturg'],
      choreographer: [240, 210, 'agent', 'Choreographer', 'avis technique', 'choreographer'],
      policy: [430, 90, 'script', 'Politique', 'specs seulement'],
      specs: [600, 90, 'script', 'PR des specs', 'merge sans CI'],
      publish: [780, 90, 'script', 'Issue publiée', 'proposed / ready'],
      director: [960, 90, 'human', 'Director', 'accepte l\'issue', 'director'],
    },
    edges: [['begin', 'dramaturg'], ['dramaturg', 'choreographer', 'ask'], ['choreographer', 'dramaturg', 'ask'], ['dramaturg', 'policy'],
      ['policy', 'specs'], ['specs', 'publish'], ['publish', 'director']],
  },
};

/* Quel nœud chaque événement touche. */
function nodeOfEvent(e, kind) {
  const d = e.detail;
  switch (e.event) {
    case 'begin': return 'begin';
    case 'handoff': return kind === 'rehearsal' && d.role === 'choreographer' ? 'plan' : d.role;
    case 'message': return kind === 'rehearsal' && d.from === 'choreographer' ? 'plan' : d.from;
    case 'policy': return d.role === 'dancer' && kind === 'rehearsal' ? 'policy' : kind === 'workshop' && d.role === 'dramaturg' ? 'policy' : null;
    case 'proof-start': case 'proof-end': return 'proof';
    case 'mutation-start': case 'mutation-end': case 'mutation-wake': return 'mutation';
    case 'diff-size': return 'size';
    case 'escalate': case 'director-decision': return 'director';
    case 'published': return 'publish';
    case 'done': return kind === 'rehearsal' ? 'premiere' : null;
    default: return null;
  }
}

function graphState(kind, events) {
  const visits = {}, bad = {}, path = [];
  for (const e of events) {
    let n = nodeOfEvent(e, kind);
    if (kind === 'workshop' && e.event === 'done') { path.push('specs'); visits.specs = 1; continue; }
    if (!n) continue;
    if (['handoff', 'proof-start', 'mutation-start', 'begin', 'escalate', 'diff-size', 'published'].includes(e.event) || (e.event === 'policy')) visits[n] = (visits[n] || 0) + 1;
    if ((e.event === 'proof-end' || e.event === 'mutation-end') && !e.detail.passed) bad[n] = true;
    if (e.event === 'message' && e.detail.verdict === 'REJECTED') bad[n] = true;
    if (path.at(-1) !== n) path.push(n);
  }
  if (kind === 'workshop' && events.some(e => e.event === 'published' && e.detail.status === 'proposed')) path.push('director');
  const travelled = {};
  for (let i = 1; i < path.length; i++) { const k = path[i - 1] + '>' + path[i]; travelled[k] = (travelled[k] || 0) + 1; }
  const active = activeStep(events);
  let now = active && GRAPHS[kind].nodes[active.node] ? active.node : null;
  if (active?.node === 'choreographer' && kind === 'rehearsal') now = 'plan';
  if (kind === 'workshop' && path.at(-1) === 'director') now = 'director';
  return {visits, bad, travelled, now};
}

function diagram(kind, events, {compact = false, selectable = false, selected = ''} = {}) {
  const g = GRAPHS[kind], st = graphState(kind, events);
  const W = compact ? 84 : 100, H = compact ? 40 : 48;
  const edge = ([a, b, type]) => {
    const [x1, y1] = g.nodes[a], [x2, y2] = g.nodes[b], k = a + '>' + b, n = st.travelled[k] || 0;
    let d;
    if (type === 'back') { const lift = 30 + (x1 - x2) / 12; d = `M${x1},${y1 - H / 2} C${x1},${y1 - H / 2 - lift} ${x2},${y2 - H / 2 - lift} ${x2},${y2 - H / 2}`; }
    else if (type === 'skip') d = `M${x1 + W / 2 - 10},${y1 + H / 2} C${x1 + 60},${y1 + 70} ${x2 - 60},${y2 + 70} ${x2 - W / 2 + 10},${y2 + H / 2}`;
    else if (type === 'esc') d = `M${x1},${y1 + H / 2} L${x2},${y2 - H / 2}`;
    else if (type === 'ask') { const off = a === 'dramaturg' ? -14 : 14; d = `M${x1 + off},${y1 + (y2 > y1 ? H / 2 : -H / 2)} L${x2 + off},${y2 + (y2 > y1 ? -H / 2 : H / 2)}`; }
    else d = `M${x1 + W / 2},${y1} L${x2 - W / 2},${y2}`;
    const mid = type === 'back' ? [(x1 + x2) / 2, y1 - H / 2 - 30 - (x1 - x2) / 12 + 6] : [(x1 + x2) / 2, (y1 + y2) / 2 - 6];
    return `<path class="edge e-${type || 'main'} ${n ? 'travelled' : ''}" d="${d}" marker-end="url(#arrow${n ? '-on' : ''})"/>` +
      (n > 1 ? `<text class="edge-count" x="${mid[0]}" y="${mid[1]}">×${n}</text>` : '');
  };
  const node = ([id, [x, y, type, label, sub, who]]) => {
    const v = st.visits[id] || 0, cls = ['node', `n-${type}`, v ? 'visited' : '', st.now === id ? 'now' : '', st.bad[id] ? 'bad' : '', selected === id ? 'selected' : ''].join(' ');
    const shape = type === 'agent' ? `<rect x="${x - W / 2}" y="${y - H / 2}" width="${W}" height="${H}" rx="${H / 2}"/>`
      : type === 'human' ? `<polygon points="${x - W / 2},${y} ${x - W / 2 + 14},${y - H / 2} ${x + W / 2 - 14},${y - H / 2} ${x + W / 2},${y} ${x + W / 2 - 14},${y + H / 2} ${x - W / 2 + 14},${y + H / 2}"/>`
      : `<rect x="${x - W / 2}" y="${y - H / 2}" width="${W}" height="${H}" rx="4"/>`;
    const glyph = type === 'agent' ? '◆' : type === 'human' ? '●' : '⚙';
    return `<g class="${cls}" ${who ? `style="--r:var(--${who})"` : ''} ${selectable ? `data-node="${id}" tabindex="0" role="button"` : ''}>${shape}
      <text class="n-label" x="${x}" y="${y - (compact ? 1 : 3)}">${glyph} ${esc(label)}</text>${compact ? '' : `<text class="n-sub" x="${x}" y="${y + 13}">${esc(sub)}</text>`}
      ${v > 1 ? `<g class="n-badge"><circle cx="${x + W / 2 - 4}" cy="${y - H / 2 + 2}" r="9"/><text x="${x + W / 2 - 4}" y="${y - H / 2 + 6}">${v}</text></g>` : ''}</g>`;
  };
  return `<svg class="diagram ${compact ? 'compact' : ''}" viewBox="0 0 ${g.w} ${g.h}" role="img" aria-label="Diagramme d'états">
    <defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="arrowhead"/></marker>
    <marker id="arrow-on" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" class="arrowhead on"/></marker></defs>
    ${g.edges.map(edge).join('')}${Object.entries(g.nodes).map(node).join('')}</svg>`;
}
const legend = () => `<div class="legend"><span><i class="lg-agent"></i>agent</span><span><i class="lg-script"></i>étape du script (déterministe)</span><span><i class="lg-human"></i>Director</span><span><i class="lg-now"></i>en cours</span><span><i class="lg-bad"></i>rouge / rejet</span></div>`;

/* --- le fil (comme la v1) ------------------------------------------------------------------------ */

const TALK = new Set(['message', 'handoff', 'nudge', 'director-decision', 'escalate', 'published']);
const HOW = {start: 'lancé', send: 'relancé', reply: 'réponse'};

function thread(events, {filter = 'all', kind = 'rehearsal', node = ''} = {}) {
  const rows = events.filter(e => (filter === 'all' || (filter === 'talk') === TALK.has(e.event)) && (!node || nodeOfEvent(e, kind) === node));
  if (!rows.length) return '<p class="empty">Rien pour ce filtre.</p>';
  let lastDay = '';
  return `<ol class="thread">${rows.map(e => {
    const d = dayOf(e.at), sep = d !== lastDay ? `<li class="sep-day">${d}</li>` : ''; lastDay = d;
    return sep + eventRow(e);
  }).join('')}</ol>`;
}

function eventRow(e) {
  const d = e.detail, t = `<time>${clock(e.at)}</time>`;
  const bubble = (who, meta, body = '', cls = '') => `<li class="ev ${cls}"><span class="avatar" style="--r:var(--${who})">${(ROLE_NAMES[who] || '?')[0]}</span><div class="bubble">${meta}${t}${body}</div></li>`;
  const line = (html, tone = '', extra = '') => `<li class="ev line ${tone}"><span class="tick"><i></i></span><div class="lbody">${html}${t}${extra}</div></li>`;
  const pre = txt => txt ? `<pre class="text">${esc(txt)}</pre>` : '';
  switch (e.event) {
    case 'message': {
      const tone = d.verdict === 'APPROVED' ? 'ok' : d.verdict === 'REJECTED' ? 'bad' : d.type === 'question' ? 'warn' : '';
      return bubble(d.from, `<div class="meta">${role(d.from)} → ${role(d.to)} <span class="badge ${tone}">${esc(d.verdict || d.type)}</span><span class="muted">tour ${esc(d.round)}</span></div>`, pre(d.text));
    }
    case 'handoff': return bubble('conductor', `<div class="meta">${role('conductor')} → ${role(d.role)} <span class="badge">${HOW[d.how] || d.how}</span>${d.model ? `<span class="muted">${esc(d.agent)} ${esc(d.model)}</span>` : ''}</div>`, pre(d.text), 'handoff');
    case 'begin': return line(`<b>Ouverture</b> de ${esc(d.item)}${d.request ? ` · demande « ${esc(d.request)} »` : ''}${d.picked ? ' · choisi dans Next up' : ''}`);
    case 'policy': return line(`<b>Politique</b> · ${role(d.role)} ${d.violations?.length ? `: ${d.violations.length} violation(s)` : 'en règle'}`, d.violations?.length ? 'bad' : '');
    case 'proof-start': return line('<b>Preuve</b> lancée par le script', 'run');
    case 'proof-end': return line(`<b>Preuve</b> ${d.passed ? 'verte' : 'rouge'} · ${d.seconds} s`, d.passed ? 'ok' : 'bad');
    case 'mutation-start': return line(`<b>Mutation</b> lancée en arrière-plan · ${esc(d.tool)}${d.files ? `, ${d.files} fichiers` : ''}`, 'run');
    case 'mutation-end': return line(`<b>Mutation</b> ${d.passed ? 'verte' : 'rouge'} · ${d.seconds} s${d.details ? ` · ${esc(d.details)}` : ''}`, d.passed ? 'ok' : 'bad');
    case 'diff-size': return line(`<b>Diff</b> : ${d.counted} lignes sur ${d.limit}${d.over ? ' · au-dessus' : ''}`, d.over ? 'warn' : '');
    case 'wait': return line(`<b>Script</b><ul class="steps">${(d.done || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul>`, 'quiet');
    case 'escalate': return line(`<b>Escalade</b> : ${esc(d.reason)}`, 'warn');
    case 'director-decision': return line(`${role('director')} décide : <b>${esc(d.verdict)}</b>`, 'ok');
    case 'handover': return line(`<b>Passage de main</b> : le worktree joue ${esc(d.to)}`, 'ok');
    case 'published': return line(`<b>Issue #${d.issue} publiée</b> · ${esc(d.type)} ${esc(d.item)}, <span class="badge warn">${esc(d.status)}</span> · ${d.decided_alone} décisions prises seul`, 'ok');
    case 'done': return line(`<b>Terminé</b> : ${esc(d.reason)}`, 'ok', d.done ? `<ul class="steps">${d.done.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : '');
    default: return line(`<b>${esc(e.event)}</b>`);
  }
}

/* --- chiffres ----------------------------------------------------------------------------------- */

/* Le temps passé par les agents et par le script dans un fil. */
function split(events) {
  let agent = 0, script = 0;
  events.forEach((e, i) => {
    if (e.event === 'handoff') {
      const back = events.slice(i + 1).find(x => x.event === 'message' && (x.detail.from === e.detail.role));
      agent += minutes(e.at, back ? back.at : NOW);
    }
    if (e.event === 'proof-end' || e.event === 'mutation-end') script += (e.detail.seconds || 0) / 60;
  });
  return {agent: Math.round(agent), script: Math.round(script)};
}

function featureStats(f) {
  const slices = sliceOf(f), all = REHEARSALS.filter(r => r.feature === f.id);
  const starts = all.map(r => r.start).filter(Boolean).sort(), ends = all.map(r => r.end).filter(Boolean).sort();
  const live = all.some(r => r.status === 'open');
  const events = all.flatMap(r => eventsOf(r.id)), sp = split(events);
  return {
    slices: slices.length, done: slices.filter(r => r.status === 'done').length,
    status: live ? 'open' : slices.every(r => r.status === 'done') ? 'done' : 'next',
    wall: starts.length ? minutes(starts[0], live ? NOW : ends.at(-1)) : 0,
    rt: slices.reduce((s, r) => s + r.rt, 0), lines: slices.reduce((s, r) => s + r.size, 0),
    mut: slices.reduce((s, r) => s + r.mut, 0), director: all.filter(r => r.director).length,
    agent: sp.agent, script: sp.script, rejected: events.filter(e => e.detail.verdict === 'REJECTED').length,
  };
}

const directorInbox = () => [
  {kind: 'escalation', id: 'TASK-004', text: 'Escalade : preuve rouge 3 fois sur TASK-004', at: '2026-11-20T21:02Z', href: 'rehearsal/TASK-004'},
  {kind: 'proposed', id: 'FEAT-008', text: '#63 FEAT-008 proposée par un Workshop autopilot, 4 décisions prises seul', at: '2026-11-20T18:24Z', href: 'program'},
];

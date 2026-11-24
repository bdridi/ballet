{"ballet": "message", "from": "choreographer", "to": "dramaturg", "type": "question", "subject": "FEAT-NNN", "round": 1}

1. <point> — <reference>. Recommendation: <…>

<!-- The one format of every message between Ballet roles.

     Line 1: the header, one line of JSON, nothing else on it. The Conductor reads only this line:
     it routes on `to`, counts the rounds per subject and pair of roles, and escalates to the Director
     beyond `[escalation] max_exchange_rounds`. A first line that is not valid JSON is sent back.
       ballet   always "message"
       from, to dramaturg | choreographer | dancer | critic | conductor | director
       type     question | answer | report | verdict | escalation | revise | approve | override
       subject  FEAT-NNN, BUG-NNN, TASK-NNN, or the issue "#N" once created
       round    integer: the exchange round on this subject, between these two roles

     Then a blank line and the body, in Markdown, in the specs language. Never JSON-escaped.
       question:   numbered points, each with its reference (`@FEAT-NNN-Cn`, a glossary entry, a file)
                   and the sender's recommendation.
       answer:     one line per question point, by number. When the answer is a change in the specs,
                   name the commit and the files; never paste the diff: the asker re-reads the specs.
       report:     what the role did, at the end of its run (see each role's report).
       verdict:    first body line `VERDICT: APPROVED`, `VERDICT: REJECTED` or `VERDICT: ESCALATE`.
       escalation: the reason, and what the Director must decide.
       revise:     the Director only, in a plan review: numbered remarks the Choreographer takes in its plan.
       approve:    the Director only, in a plan review: the plan is approved, the Dancer starts.
       override:   the Director only, `to: conductor`: lifts what blocks the Rehearsal when no question waits (a policy
                   refusal, a worker that failed, a diff too big, too many rounds). The body is the Director's reason, in their
                   words: the worker it restarts, and the Rehearsal's journal and issue, read it. An `answer` only answers a question.
     This comment is not part of a message. -->

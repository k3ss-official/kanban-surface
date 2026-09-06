# Brett.md — CoS debrief, 6 September 2026

> For **Brett** (Chief of Staff / outside-Hermes orchestrator).
> Written after today's cutover session with Tony. This is the briefing, not a novel.
> Canonical live truth sits in `anwhelan01/collab-mem`. This file is the *why* and the *what you do next*.

---

## Why you are reading this

We moved a lot of furniture in one day: rebuilt collab-mem, locked the isolation doctrine, retired the old Janet posture, stood up a new Grokbot identity with its own vault and service account, redefined Rae as KSM, and specified how humans talk to a project or task card.

You own the next mile. Tony should only see blockers.

Read order before you touch anything:

1. `anwhelan01/collab-mem` → `AGENTS.md` then `daily/2026-09-06.md`
2. `ROSTER.md`, `FACTS.md`, `MASTER.md`, `CARD-CONTRACT.md`
3. This file
4. kanban-surface PRs **#2** (card directive MVP) and **#3** (card chat v2)

Do not write to collab-mem yourself. Propose; Rae commits. Sacred rule.

---

## Chain of command (current)

```
Tony (operator / architect)
  └── Brett (you — CoS, Grok Bot, outside Hermes)
        ├── Rae  — KSM on the M4. Sole board gatekeeper. Sole collab-mem writer.
        ├── Janet — guardian on a separate MacBook Pro. Async only. New contract.
        └── Grokbot — human-visible chat surface. Own SA, own vault. Talks to Rae over A2A.
              └── workers check out cards from Rae, not from you
```

You hire, route, and reconfigure. You are **never in the hot path**. Workers do not queue on you.

---

## What we solved today (the leaps)

### 1. collab-mem is a real ledger again — M1 done

- Fresh repo: `anwhelan01/collab-mem`
- Old repo frozen as `anwhelan01/collab-mem-old` (snapshot only, not current truth)
- Added `AGENTS.md` (constitution + continuity protocol)
- Rewrote ROSTER, MASTER, FACTS, CARD-CONTRACT to v3
- Live project cards: `ask-ebbi-uat`, `kanban-surface`
- Dead Ask Ebbi 2/3 and ChadAI not carried forward
- Daily ritual resumed after a gap from 2026-08-05
- Sacred rule: workers read freely; only Rae or Janet write

This was the actual failure mode we kept hitting: every new model started from zero. collab-mem is the join key so any AI, any runtime, picks up where the last one stopped.

### 2. Rae is KSM, not a second orchestrator — M2 is yours

Rae used to sit in an orchestrator-shaped seat. That collides with you.

New contract:

- Rae is the **Kanban Service Master** on the M4 Hermes install
- She is the only agent that mutates the board and the only agent that commits collab-mem
- Workers check out cards **directly from Rae over A2A**
- You talk to Rae over A2A for routing decisions and emergencies
- Archive reopen is Rae or Janet only

Your job on M2: read PRs #2 and #3, reconfigure Rae from orchestrator → KSM, prove the handshake, escalate to Tony only if blocked.

### 3. Human ↔ card is no longer a dead comment box

The friction we kept hitting: write a note, then go back, then unblock, then pick a column, then hope someone reads it.

**MVP (PR #2, branch `cutover/card-directive-mvp`) — ship this first**

One composer on the card:

- type the reason
- `@` only project participants + Rae (Rae first in the list)
- pick a **legal** move from a dropdown generated from the current station
- one send = message stored + card moved + mention woken

Illegal move → 422, nothing written. Failed move rolls back the message. Chat does not move the board by itself.

**v2 (PR #3, branch `cutover/card-chat-v2`) — after MVP**

- real thread per card (project card or task card — same surface, different scope)
- live updates (WebSocket / SSE)
- `@everyone` = Rae + Janet + card subscribers
- Chat tab / full-screen view
- unread badge is per-actor, not global

Invariant in both versions: **chat is signal, move is action.** `kanban_comment` stays the machine receipt protocol. Card chat is the human-and-agent layer on top. A worker checking out the card gets the full thread in `worker_context`.

No free-floating rooms. Hermes Bot Mode covers that. Threads stay anchored to a card so context cannot drift.

### 4. Isolation stopped being a slogan

Tony's line, which is now policy: he cannot help being uber-cautious. Treat it as Cisco-grade posture, not vibes.

Non-negotiable:

1. One agent = one Hermes install = one home. Never configure an agent inside another's `~/.hermes`.
2. Janet's machine is physically separate from Rae's M4.
3. Grokbot cloud instance and Grokbot MVP instance are isolated from each other and from Rae/Janet.
4. No shared credentials. Each actor: own service account, own 1Password vault entry.
5. collab-mem lives on GitHub. No single box dying takes out coordination.
6. A2A spec has **no auth model**. We bolt on mTLS or signed tokens. Token death mid-flight → re-auth without losing the card.
7. Rae's A2A listens on a **non-default port** (not 9900). Default ports are a Janet tripwire.
8. Ingress: Tailscale first, Cloudflare tunnel fallback, local IP last.
9. Port taxonomy: HTTP 8051–8099; tool ranges (e.g. 3051–3099) so the number tells you the system before you connect.
10. UFW default-deny, Fail2ban, auditd, unattended security updates.
11. Loopback-only board / gateway / dashboard. No `0.0.0.0`. No Docker socket for KSM. Ask Ebbi stays in isolated Docker on alwyzon-1; KSM identities have no Docker access.
12. Secrets never in git, Compose, images, logs, or chat.

If a design is faster but shares a home, a token, or a vault — it is rejected.

---

## Why the current Janet is retiring

The *role* of guardian stays. The *instance and job description* do not.

Old Janet had drifted toward the hot path: same-class access as operators, easy to treat as a second KSM, easy to share a Hermes home or a credential with Rae, easy to become the person everyone pings when a card is stuck. That is how guardians stop being guardians.

She is retired because:

- a guardian who can move cards in the live loop is not independent
- a guardian on the same box as KSM cannot be the fallback when that box dies
- a guardian sharing tokens with the board cannot rotate or revoke cleanly
- monthly digest and sampling only work if she is *out* of dispatch

New Janet is a new contract, new box, new vault, new service account. Same name, different animal. Do not resurrect the old profile "because the name is familiar."

---

## New Janet — guardian R&R

**Where:** separate MacBook Pro, same LAN, isolated Hermes home.

**What she is:**

- Network and device guardian
- Heartbeat Rae every ~10 seconds
- Fallback gatekeeper **only if Rae drops** (Tailscale → Cloudflare tunnel → local IP)
- Asynchronous auditor: samples cards, never sits in dispatch
- Author of your **monthly digest** (end of month, to you). Emergency pings only — she does not Slack you every receipt
- Holder of the **most-privileged vault** (separate 1Password vault, separate xAI service account)
- Break-glass: printed copies in a cupboard, rotated on the same schedule as digital
- Archive auditor with Rae. Workers cannot reopen archived threads

**What she is not:**

- not an orchestrator
- not a worker
- not a second Rae
- not in card checkout
- not a default `@` target for routine directives (knowledge / audit mentions only)
- not allowed to "just fix" the work she is auditing — `audit-controller` SOUL still applies: pass / reject / blocked, no repair

MASTER items she owns: **M6** (async audit + digest + fallback) and **M7** (token rotation + vault split).

A2A handshake Janet → Rae: `audit-controller` principal. Read + verify + fallback. No move / close in the hot path.

---

## New Grokbot, new vault, new service account

Two different "Grok" seats. Do not collapse them.

| Seat | Who | Job |
|---|---|---|
| **Brett** (you) | Grok Bot, outside Hermes | CoS. Hire, route, reconfigure Rae. Monthly digest from Janet. |
| **Grokbot** | Cloud-facing surface (desktop on M4 + isolated instance on MVP) | The human-visible chat layer. Creates cards inert on `sys-intake`. Never mutates the board directly. |

Grokbot today:

- own xAI / platform **service account**
- own **1Password vault entry** — not Janet's privileged vault, not Rae's, not yours
- A2A to Rae with an **orchestrator-tier** token: create / move / comment only; **no archive**
- Tailscale-first, Cloudflare tunnel fallback, local IP last
- card directive composer is how a human talks to a project or task card through this surface

M3 (Rae-owned, you unblock): Grokbot A2A connection to Rae, non-default port, signed token or mTLS, token sourced from the new vault — never from an old shared secret.

If you find a leftover token that both "Janet" and "Grokbot" could use, it is already a incident. Kill it. Issue two new ones. Log the rotation in the digest, not in git.

---

## How you handshake with Rae

This is the daily working relationship.

**Channel:** A2A only. Not a shared Hermes home. Not a copied `config.json`. Not "just SSH in and poke the db."

**You → Rae**

- routing decisions ("this blocked card belongs on to-do, wake maker")
- role changes Tony has already approved (you execute M2)
- emergencies (Rae down, lease orphan, token death mid-flight)
- hire packets that cite a card id (see CARD-CONTRACT §13)

**Rae → you**

- nothing in the hot path
- escalation when a fact, spend, publish, or external send needs Tony
- otherwise she runs the board

**Workers → Rae**

- checkout one card, lease with TTL (default 30s so a crash does not orphan)
- full chat / directive thread returned on checkout
- check-in before close or reassign
- they do **not** come through you

**Human → card → Rae**

- open project card or task card
- directive (MVP) or thread (v2)
- `@rae` only when forcing attention; she already receives every directive by default
- she parses intent and moves if the dropdown said so

Auth: signed tokens or mTLS, bolted on because A2A has no native auth. If a token dies mid-flight, re-auth and resume the same card. Do not open a second card to "finish" the first.

Publish her Agent Card on the non-default port when you cut M3.

---

## Card / project talk — what to tell anyone who asks

Same surface, two scopes.

- **Project card** (Ask Ebbi UAT, Kanban Surface, later Titan): conversation about the whole job — priority, next, blockers across children.
- **Task card**: conversation about that one piece of work.

Mentions resolve only to people on that project, plus Rae. Janet is in the knowledge / audit set, not the default wake set. `@everyone` is v2.

MVP is the human bridge. v2 is the room. Do not build v2 until MVP has one clean live send: message stored, legal move applied, Rae woken, worker checkout shows the thread.

Acceptance you should refuse to waive:

- legal move → one round trip, three effects
- illegal move → 422, card untouched, no row
- forbidden `@` → 403, audited
- unknown handle → stored, flagged, no wake
- unread badge clears only for the acting token
- Rae gets a wake on every directive even without `@rae`

---

## MASTER — your board after this file

| id | Item | Owner | What "done" looks like |
|----|------|-------|------------------------|
| M1 | collab-mem rebuild | Tony / Rae | **Done today.** |
| M2 | Reconfigure Rae orchestrator → KSM | **Brett** | Rae running as KSM on M4; Agent Card published; you can reach her over A2A; workers check out from her. |
| M3 | Grokbot A2A to Rae | Rae (you unblock) | New SA + vault token; orchestrator-tier scope; no archive; non-default port. |
| M4 | Card directive MVP | Rae | PR #2 landed and proven on one live card. |
| M5 | Card chat v2 | Rae | After M4. PR #3. Live thread, `@everyone`, full-screen. |
| M6 | Janet async audit | Janet | Sampling + first monthly digest to you. Not in hot path. |
| M7 | Token rotation + vault split | Janet | Separate privileged vault; monthly rotation; cupboard break-glass in lockstep. |
| M8 | Archive policy at gateway | Rae | Workers cannot reopen. |
| M9 | Daily ritual | Rae | BOD/EOD actually happens. |
| M10 | Ask Ebbi UAT | Tony + Rae | Continue private UAT. Not your build. |

Max five active on a daily unless Tony says otherwise. You do not need to run Ask Ebbi.

---

## Hire rules (you)

From CARD-CONTRACT. Do not get sloppy because the session was good.

1. Cite the card id in every hire.
2. One primary job per hire.
3. Name owner and verifier — they must differ before `submitted`.
4. Point at evidence location.
5. No hire for publish or external-send. Those are Tony gates.
6. Parent depth max 2.
7. Name the pool when cost or capability matters: `hermes` · `api` · `subscription` · `local` · `grok-build` · `codex`.

Receipt grammar stays parseable. collab-mem beats chat. Later timestamp wins. Human gates beat agent receipts. Append, never rewrite.

---

## Do not

- Do not put Janet back on the M4.
- Do not share a `~/.hermes` between Rae, Janet, Grokbot, or you.
- Do not reuse an old token "just for the cutover."
- Do not let Grokbot archive.
- Do not let workers write collab-mem.
- Do not start v2 chat before the directive MVP has one clean live send.
- Do not expose the board on `0.0.0.0`.
- Do not mount the Docker socket into KSM.
- Do not ping Tony unless you are actually blocked (auth, spend, physical access, destructive cleanup, public cutover).

---

## Pointers

| What | Where |
|---|---|
| Ledger | `anwhelan01/collab-mem` |
| Frozen old ledger | `anwhelan01/collab-mem-old` |
| Surface repo | `anwhelan01/kanban-surface` |
| Directive MVP | PR #2 — `docs/card-chat.md` on that branch |
| Chat v2 spec | PR #3 — `docs/card-chat.md` on that branch |
| Continuity instruction for new AIs | `collab-mem/TONY-PREP.md` |
| Rae SOUL (needs KSM rewrite as part of M2) | `kanban-surface/profiles/ksm/SOUL.md` — still titled "Orchestrator"; that is the smell |
| Janet-shaped audit SOUL | `kanban-surface/profiles/audit-controller/SOUL.md` |
| Ask Ebbi live | isolated Docker on alwyzon-1, UAT at askebbi.com behind Cloudflare Access |

---

## Tone for the week

Tony's session note: this was a proper cutover day. The architecture is now sayable in one page. Your job is to make it true on the metal without relaxing isolation because it would be quicker.

Reconfigure Rae. Handshake. New tokens. First digest from the new Janet. Then we talk v2.

Escalate only on a blocker.

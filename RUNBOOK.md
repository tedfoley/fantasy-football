# Weekly management runbook

This is the procedure the weekly Devin automation follows for Ted's three ESPN
leagues. Run everything from the repo root with `ESPN_S2` and `ESPN_SWID` set.

```
pip install -r requirements.txt
python ff.py leagues
```

Leagues (aliases work anywhere `--league` is accepted): `ginger` (832310474,
10 teams, FAAB 100), `winter` (803340783, 12 teams, FAAB 100), `dalton`
(1356551957, 8 teams, FAAB 1000). All are H2H, full PPR, no trades.
Lineup: QB, RB x2, WR x2, TE, FLEX (RB/WR/TE), D/ST, K; 7 bench; IR (1, Dalton 3).
Slot ids: QB=0 RB=2 WR=4 TE=6 D/ST=16 K=17 BE=20 IR=21 FLEX=23.

Waivers in all three leagues run 24h daily: any player dropped (or who was
rostered when the week's games ended) sits on waivers ~1 day, then becomes a
free agent. FAAB bids are blind.

## Runs

| When (ET)     | Mode     | Purpose |
|---------------|----------|---------|
| Tue 8:07 pm   | WAIVERS  | Week is final. Review what happened, submit FAAB claims (process Wed morning), do FA add/drops, fix IR. |
| Thu 4:07 pm   | LINEUP   | Full lineup for the coming week, before TNF kickoff (8:15 pm). |
| Sun 10:37 am  | LINEUP   | Final pass after Sunday inactives/news; emergency FA fills. Only unlocked players can move. |

The triggering event says which mode it is; if unclear, infer from the day.

## 1. Gather (every run, every league)

1. `python ff.py --json leagues` — record, week, FAAB left, opponent.
2. `python ff.py --json schedule` — kickoff times this week (lock times).
3. `python ff.py --json roster --league <L>` — for each league.
4. `python ff.py --json free-agents --league <L> --limit 40` overall and with
   `--pos RB`, `--pos WR`, `--pos TE`, `--pos QB` as needed.
5. `python ff.py --json transactions --league <L>` — see what cleared / what
   other managers did.

## 2. Research (do not rely on ESPN projections alone)

ESPN's `proj` field is one input, not the answer. Before deciding, check the
open web for the current week:

- Injuries/inactives: official team reports (Wed–Fri practice designations,
  Sunday inactives ~90 min before kickoff), ESPN/NFL.com injury pages,
  beat-reporter updates. Treat OUT/DOUBTFUL as unstartable; QUESTIONABLE needs
  a specific read (practice trend, beat reports).
- Usage/role changes from last week: snap share, target share, carries,
  red-zone touches, backfield committees, new starters after injuries.
- Matchups: opposing defense vs position (allowed pts/yards, pass-funnel vs
  run-funnel), Vegas totals/spreads (game script), pace.
- Weather for outdoor games (wind > 15 mph or heavy rain hurts K, deep WRs, QBs).
- Bye weeks — a starter on bye scores 0.
- Consensus start/sit and waiver rankings from a couple of independent sources
  (e.g. FantasyPros ECR, Establish The Run, Rotoworld/NBC, The Athletic,
  Reddit r/fantasyfootball threads) to sanity-check, not to copy.

Keep notes with sources; the summary at the end must cite the reasons.

## 3. Lineup decisions (LINEUP runs; also fix obvious holes in WAIVERS runs)

For each league, build the lineup that maximizes expected points with
reasonable floor, given the matchup:

- Never start a player who is OUT, DOUBTFUL, on bye, or already ruled inactive.
- If I'm a heavy favorite this week, prefer floor; if underdog, prefer ceiling.
- FLEX: best remaining RB/WR/TE by expected PPR points; PPR favors
  high-target players.
- D/ST and K: stream by matchup if the free agent is clearly better and the
  roster spot is free or the drop is painless.
- IR slot: only players with injuryStatus OUT/IR are eligible; if an IR player
  is healthy ESPN blocks other moves until they're activated — fix that first.
- Respect locks: `locked: true` players cannot be moved; on Sunday runs only
  touch players whose games haven't kicked off. Also don't empty a slot whose
  player has a late game just because their replacement is uncertain.

Apply moves with one command per league so the swap is atomic:

```
python ff.py set-lineup --league winter --move <starterId>:20 --move <benchId>:6 --dry-run
python ff.py set-lineup --league winter --move <starterId>:20 --move <benchId>:6
```

Confirm with `roster` afterwards. Skip a league entirely if the lineup is
already correct — don't churn.

## 4. Waiver / free agent decisions (WAIVERS runs; emergencies on other runs)

Be selective. The goal is a better team, not activity. Add someone when:

- A starter or key bench piece is out multi-week and a free agent has a real
  role (e.g. the new lead back after an injury, a WR2 stepping into WR1 targets).
- A free agent's role clearly changed (usage last week + beat-reporter
  confirmation), and they'd start for me or beat my worst bench player.
- I need a bye-week fill or a D/ST/K stream and the drop is a dead roster spot.

Do not add: one-week touchdown spikes with no usage change, players behind a
healthy starter, or anyone who requires dropping a player I'd want back.

Drops: lowest expected value over the rest of the season — handcuffs of other
teams' RBs, D/ST/K after their stream, injured non-IR-eligible players with
long timelines, WR5/6 with no path to targets. Never drop someone starting
this week for an equivalent player.

FAAB bidding (blind): budgets are 100 (ginger, winter) and 1000 (dalton).
- Must-have league-winner (new every-down RB, etc.): 25–40% of remaining.
- Solid starter upgrade: 8–15%.
- Speculative/depth: 1–5%.
- Streamers: 0–2%.
Never spend more than ~50% of remaining budget in one week. Scale by league
size: shallower (8-team dalton) means the FA pool is stronger, so bid less.
Prefer the claim on the best target; add a backup claim on a second target
only if the drop candidate differs or it's cheap.

Commands:

```
python ff.py add --league ginger --add <pid> --drop <pid> --bid 12 --dry-run
python ff.py add --league ginger --add <pid> --drop <pid> --bid 12
python ff.py add --league ginger --add <pid> --drop <pid>          # FA, no bid
```

`add` auto-detects whether the player is on waivers (claim) or a free agent
(instant). Confirm with `transactions` (pending claims) or `roster`.

## 5. Report

Finish the session with a short summary per league:

- Record and this week's opponent.
- Lineup changes made (or "no changes") with one-line reasons and sources.
- Waiver claims/adds/drops with bids and reasons.
- Anything needing Ted's attention (e.g. a claim that will need a decision,
  cookie expiring — `ESPN_S2` failing with 401/403 means it must be refreshed).

# fantasy-football

Small Python CLI to read and write ESPN fantasy football leagues via ESPN's
(unofficial) JSON API with cookie auth.

## Setup

```sh
pip install -r requirements.txt
export ESPN_S2='...'      # espn_s2 cookie
export ESPN_SWID='{...}'  # SWID cookie (with braces)
```

`leagues.json` lists the leagues (id -> name, alias, your teamId). Anywhere
`--league` is required you can pass the league id or its alias
(`ginger`, `winter`, `dalton`).

## Commands

```sh
python3 ff.py leagues                                  # all leagues overview
python3 ff.py roster --league ginger                   # my roster
python3 ff.py roster --league ginger --team 5          # any team's roster
python3 ff.py free-agents --league winter --pos RB --limit 10
python3 ff.py schedule                                 # this week's NFL games (ET)
python3 ff.py transactions --league dalton             # recent + pending
python3 ff.py set-lineup --league winter --move 4431459:20 --move 4570037:6
python3 ff.py set-lineup --league winter --move PID:SLOT --dry-run
python3 ff.py add --league ginger --add 4696044 --bid 3        # waiver claim
python3 ff.py add --league ginger --add 4696044 --drop 3917315 # FA add+drop
python3 ff.py add --league ginger --add 4696044 --dry-run
```

Global flags: `--json` (machine-readable output), `--season` (default 2026).
`set-lineup` refuses to move players whose game has started (locked).

## Lineup slot IDs

| id | slot | id | slot |
|----|------|----|------|
| 0  | QB   | 16 | D/ST |
| 2  | RB   | 17 | K    |
| 4  | WR   | 20 | BE (bench) |
| 6  | TE   | 21 | IR   |
| 23 | FLEX (RB/WR/TE) | | |

Default position IDs: 1 QB, 2 RB, 3 WR, 4 TE, 5 K, 16 D/ST.

## Notes

- Reads hit `lm-api-reads.fantasy.espn.com`; writes hit
  `lm-api-writes.fantasy.espn.com/.../transactions/`.
- Lineup moves: transaction `type: "ROSTER"`, `executionType: "EXECUTE"`,
  items `{playerId, type: "LINEUP", fromLineupSlotId, toLineupSlotId}`.
- Free-agent add/drop: `type: "FREEAGENT"`, items `ADD`/`DROP`.
- Waiver claim: `type: "WAIVER"`, `executionType: "PROCESS"`, `bidAmount`.
- Writes require headers `X-Fantasy-Source: kona`, `Content-Type: application/json`,
  plus the auth cookies.

#!/usr/bin/env python3
"""ESPN fantasy football CLI: read/write leagues via the JSON API."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from espn.client import (Client, ESPNError, SLOT_NAMES, BENCH_SLOTS,
                         nfl_games, describe_entry, ET)

CONFIG = Path(__file__).parent / "leagues.json"


def load_leagues():
    return json.loads(CONFIG.read_text())


def resolve_league(arg):
    leagues = load_leagues()
    for lid, info in leagues.items():
        if arg == lid or arg.lower() in (info["name"].lower(), info.get("alias", "").lower()):
            return int(lid), info
    raise SystemExit(f"unknown league: {arg!r} (known: " +
                     ", ".join(f'{i["alias"]}/{lid}' for lid, i in leagues.items()) + ")")


def emit(obj, as_json, fmt=None):
    if as_json:
        print(json.dumps(obj, indent=2, default=str))
    elif fmt:
        fmt(obj)


def print_player(p):
    lock = " LOCKED" if p["locked"] else ""
    print(f'{p["playerId"]:>9} {p["name"]:<24} {p["pos"]:<4} {p["proTeam"]:<4} '
          f'{p["slot"]:<5} inj={p["injury"] or "-":<10} own={p["pctOwned"]:>5}% '
          f'proj={p["proj"] if p["proj"] is not None else "-":>5} '
          f'last={p["last"] if p["last"] is not None else "-":>5} '
          f'opp={p["opp"] or "-":<4} {p["kickoff"] or "-":<22}{lock}'
          + (f' waiver={p["waiverStatus"]}' if "waiverStatus" in p else ""))


def cmd_leagues(args):
    c = Client(args.season)
    out = []
    for lid, info in load_leagues().items():
        d = c.league(lid)
        sp = d["status"]["currentMatchupPeriod"]
        team = next(t for t in d["teams"] if t["id"] == info["teamId"])
        rec = team["record"]["overall"]
        acq = d["settings"]["acquisitionSettings"]
        spent = team.get("transactionCounter", {}).get("acquisitionBudgetSpent", 0)
        budget = acq.get("acquisitionBudget", 0)
        opp = None
        for m in d.get("schedule", []):
            if m.get("matchupPeriodId") == sp:
                for side in ("home", "away"):
                    if m[side]["teamId"] == info["teamId"]:
                        opp_id = m["away" if side == "home" else "home"]["teamId"]
                        opp = next(t["name"] for t in d["teams"] if t["id"] == opp_id)
        row = {
            "league": info["name"], "id": lid, "alias": info.get("alias"),
            "record": f'{rec["wins"]}-{rec["losses"]}' + (f'-{rec["ties"]}' if rec["ties"] else ""),
            "week": sp, "faabRemaining": budget - spent if budget else None,
            "matchup": opp,
            "waivers": f'{acq.get("waiverHours")}h, processes {acq.get("waiverProcessHour")}:00 '
                       f'on {",".join(d[0] for d in acq.get("waiverProcessDays", []))}',
        }
        out.append(row)
    def fmt(rows):
        for r in rows:
            print(f'{r["league"]:<22} {r["record"]:<7} week {r["week"]} '
                  f'faab={r["faabRemaining"]} vs {r["matchup"]} | waivers: {r["waivers"]}')
    emit(out, args.json, fmt)


def cmd_roster(args):
    c = Client(args.season)
    lid, info = resolve_league(args.league)
    d = c.league(lid)
    sp = d["status"]["currentScoringPeriodId"] if "currentScoringPeriodId" in d["status"] else d["scoringPeriodId"]
    team_id = args.team or info["teamId"]
    team = next(t for t in d["teams"] if t["id"] == team_id)
    games = nfl_games(args.season)
    rows = [describe_entry(e, sp, games) for e in team["roster"]["entries"]]
    if args.json:
        emit({"league": info["name"], "team": team["name"], "week": sp, "roster": rows}, True)
    else:
        print(f'{info["name"]} — {team["name"]} (week {sp})')
        for p in sorted(rows, key=lambda p: p["slotId"]):
            print_player(p)


def cmd_free_agents(args):
    c = Client(args.season)
    lid, info = resolve_league(args.league)
    d = c.league(lid, views=["mStatus"])
    sp = d["scoringPeriodId"]
    games = nfl_games(args.season)
    players = c.free_agents(lid, sp, args.pos, args.limit)
    rows = []
    for pl in players:
        e = {"playerPoolEntry": pl, "lineupSlotId": 20, "injuryStatus": None}
        p = describe_entry(e, sp, games)
        p["waiverStatus"] = pl.get("status", "?")
        rows.append(p)
    if args.json:
        emit({"league": info["name"], "week": sp, "players": rows}, True)
    else:
        print(f'{info["name"]} — free agents/waivers (week {sp})')
        for p in rows:
            print_player(p)


def cmd_schedule(args):
    games = nfl_games(args.season)
    seen = set()
    out = []
    for abbr, g in games.items():
        key = frozenset((abbr, g["opponent"]))
        if key in seen:
            continue
        seen.add(key)
        out.append({"game": f'{abbr} @ {g["opponent"]}' if games[abbr]["name"].endswith(abbr) else f'{abbr} vs {g["opponent"]}',
                    "kickoff": g["kickoff_et"].strftime("%a %m/%d %I:%M%p ET"),
                    "completed": g["completed"]})
    out.sort(key=lambda g: g["kickoff"])
    emit(out, args.json, lambda rows: [print(f'{r["kickoff"]:<22} {r["game"]}') for r in rows])


def cmd_transactions(args):
    c = Client(args.season)
    lid, info = resolve_league(args.league)
    txs, pending = c.transactions(lid)
    out = {"league": info["name"], "pending": pending, "transactions": txs}
    def fmt(o):
        if o["pending"]:
            print("PENDING:")
            for t in o["pending"]:
                print(" ", json.dumps(t))
        for t in o["transactions"][:20]:
            ts = datetime.fromtimestamp(t["proposedDate"] / 1000, ET).strftime("%m/%d %H:%M")
            items = ", ".join(f'{i["type"]} {i["playerId"]}' for i in t.get("items", []))
            print(f'{ts} team={t["teamId"]} {t["type"]} {t["status"]} bid={t.get("bidAmount", 0)}: {items}')
    emit(out, args.json, fmt)


def _roster_entries(c, lid, team_id):
    d = c.league(lid)
    sp = d["scoringPeriodId"]
    team = next(t for t in d["teams"] if t["id"] == team_id)
    games = nfl_games(c.season)
    return d, sp, team, games


def cmd_set_lineup(args):
    c = Client(args.season)
    lid, info = resolve_league(args.league)
    _, sp, team, games = _roster_entries(c, lid, info["teamId"])
    roster = {e["playerPoolEntry"]["player"]["id"]: e for e in team["roster"]["entries"]}
    items = []
    for mv in args.move:
        pid_s, slot_s = mv.split(":")
        pid, to_slot = int(pid_s), int(slot_s)
        e = roster.get(pid)
        if not e:
            raise SystemExit(f"player {pid} not on roster")
        p = describe_entry(e, sp, games)
        if p["locked"]:
            raise SystemExit(f"refusing: {p['name']} ({pid}) is locked")
        from_slot = e["lineupSlotId"]
        if from_slot == to_slot:
            raise SystemExit(f"{p['name']} already in slot {to_slot}")
        moving = {int(m.split(":")[0]) for m in args.move}
        if to_slot not in BENCH_SLOTS:
            displaced = next((x for x in team["roster"]["entries"]
                              if x["lineupSlotId"] == to_slot
                              and x["playerPoolEntry"]["player"]["id"] not in moving), None)
            if displaced:
                dp = describe_entry(displaced, sp, games)
                if dp["locked"]:
                    raise SystemExit(f"refusing: {dp['name']} occupying slot {to_slot} is locked")
                print(f'note: {dp["name"]} occupies slot {to_slot}; include a --move for them too')
        items.append({"playerId": pid, "type": "LINEUP",
                      "fromLineupSlotId": from_slot, "toLineupSlotId": to_slot})
        print(f'{p["name"]}: {p["slot"]} -> {SLOT_NAMES.get(to_slot, to_slot)}')
    payload = {"isLeagueManager": False, "teamId": info["teamId"], "type": "ROSTER",
               "memberId": c.swid, "scoringPeriodId": sp,
               "executionType": "EXECUTE", "items": items}
    if args.dry_run:
        print(json.dumps(payload, indent=2))
        return
    print(json.dumps(c.submit_transaction(lid, payload), indent=2)[:2000])


def cmd_add(args):
    c = Client(args.season)
    lid, info = resolve_league(args.league)
    _, sp, team, games = _roster_entries(c, lid, info["teamId"])
    status = None
    for pl in c.free_agents(lid, sp, limit=200):
        if pl["id"] == args.add:
            status = pl.get("status")
            name = pl["player"]["fullName"]
            break
    else:
        name = str(args.add)
    waiver = args.bid is not None or status == "WAIVERS"
    items = [{"playerId": args.add, "type": "ADD", "toTeamId": info["teamId"]}]
    if args.drop:
        items.append({"playerId": args.drop, "type": "DROP", "fromTeamId": info["teamId"]})
    payload = {"isLeagueManager": False, "teamId": info["teamId"],
               "type": "WAIVER" if waiver else "FREEAGENT",
               "memberId": c.swid, "scoringPeriodId": sp,
               "executionType": "PROCESS" if waiver else "EXECUTE",
               "bidAmount": args.bid or 0, "items": items}
    print(f'{"waiver claim" if waiver else "FA add"}: {name} (status={status})'
          + (f', drop {args.drop}' if args.drop else "") + (f', bid {args.bid}' if args.bid else ""))
    if args.dry_run:
        print(json.dumps(payload, indent=2))
        return
    print(json.dumps(c.submit_transaction(lid, payload), indent=2)[:2000])


def main():
    ap = argparse.ArgumentParser(prog="ff")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--json", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("leagues")

    p = sub.add_parser("roster"); p.add_argument("--league", required=True); p.add_argument("--team", type=int)
    p = sub.add_parser("free-agents"); p.add_argument("--league", required=True)
    p.add_argument("--pos"); p.add_argument("--limit", type=int, default=40)
    sub.add_parser("schedule")
    p = sub.add_parser("set-lineup"); p.add_argument("--league", required=True)
    p.add_argument("--move", action="append", required=True, metavar="PID:SLOT")
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("add"); p.add_argument("--league", required=True)
    p.add_argument("--add", type=int, required=True); p.add_argument("--drop", type=int)
    p.add_argument("--bid", type=int); p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("transactions"); p.add_argument("--league", required=True)

    args = ap.parse_args()
    try:
        {"leagues": cmd_leagues, "roster": cmd_roster, "free-agents": cmd_free_agents,
         "schedule": cmd_schedule, "set-lineup": cmd_set_lineup, "add": cmd_add,
         "transactions": cmd_transactions}[args.cmd](args)
    except ESPNError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()

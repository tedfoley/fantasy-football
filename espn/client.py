import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

SEASON = 2026
READ_URL = (
    "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
    "/seasons/{season}/segments/0/leagues/{league}"
)
WRITE_URL = (
    "https://lm-api-writes.fantasy.espn.com/apis/v3/games/ffl"
    "/seasons/{season}/segments/0/leagues/{league}/transactions/"
)
SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
)

SLOT_NAMES = {
    0: "QB", 2: "RB", 4: "WR", 6: "TE", 16: "D/ST", 17: "K",
    20: "BE", 21: "IR", 23: "FLEX",
}
POS_NAMES = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "D/ST"}
POS_TO_SLOT = {"QB": 0, "RB": 2, "WR": 4, "TE": 6, "K": 17, "DST": 16, "D/ST": 16}
BENCH_SLOTS = {20, 21}

PRO_TEAMS = {
    1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN",
    8: "DET", 9: "GB", 10: "TEN", 11: "IND", 12: "KC", 13: "LV", 14: "LAR",
    15: "MIA", 16: "MIN", 17: "NE", 18: "NO", 19: "NYG", 20: "NYJ", 21: "PHI",
    22: "ARI", 23: "PIT", 24: "LAC", 25: "SF", 26: "SEA", 27: "TB", 28: "WSH",
    29: "CAR", 30: "JAX", 33: "BAL", 34: "HOU",
}

ET = ZoneInfo("America/New_York")

DEFAULT_VIEWS = ["mSettings", "mTeam", "mRoster", "mMatchup", "mStatus"]


class ESPNError(Exception):
    pass


class Client:
    def __init__(self, season=SEASON):
        s2 = os.environ.get("ESPN_S2")
        swid = os.environ.get("ESPN_SWID")
        if not s2 or not swid:
            raise ESPNError("ESPN_S2 and ESPN_SWID env vars are required")
        self.season = season
        self.swid = swid
        self.session = requests.Session()
        self.session.cookies.update({"espn_s2": s2, "SWID": swid})
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        })

    def _read(self, league_id, views=None, params=None, headers=None):
        url = READ_URL.format(season=self.season, league=league_id)
        p = dict(params or {})
        if views:
            p["view"] = views
        r = self.session.get(url, params=p, headers=headers or {})
        if r.status_code != 200:
            raise ESPNError(f"GET {url} -> {r.status_code}: {r.text[:300]}")
        return r.json()

    def league(self, league_id, views=None):
        return self._read(league_id, views or DEFAULT_VIEWS)

    def free_agents(self, league_id, scoring_period, pos=None, limit=40):
        filt = {"players": {
            "filterStatus": {"value": ["FREEAGENT", "WAIVERS"]},
            "sortPercOwned": {"sortAsc": False, "sortPriority": 1},
            "limit": limit,
        }}
        if pos:
            filt["players"]["filterSlotIds"] = {"value": [POS_TO_SLOT[pos.upper()]]}
        data = self._read(
            league_id,
            views="kona_player_info",
            params={"scoringPeriodId": scoring_period},
            headers={"X-Fantasy-Filter": json.dumps(filt)},
        )
        return data.get("players", [])

    def submit_transaction(self, league_id, payload):
        url = WRITE_URL.format(season=self.season, league=league_id)
        headers = {
            "Content-Type": "application/json",
            "X-Fantasy-Source": "kona",
            "X-Fantasy-Platform": "kona-PROD",
            "Origin": "https://fantasy.espn.com",
            "Referer": "https://fantasy.espn.com/",
        }
        r = self.session.post(url, json=payload, headers=headers)
        if r.status_code not in (200, 201):
            raise ESPNError(f"POST {url} -> {r.status_code}: {r.text[:500]}")
        try:
            return r.json()
        except ValueError:
            return {"status": r.status_code}

    def transactions(self, league_id):
        data = self._read(league_id, views=["mTransactions2", "mPendingTransactions"])
        return data.get("transactions", []), data.get("pendingTransactions", [])


def nfl_games(season=SEASON, week=None):
    """NFL games for `week` (default: ESPN's current week, which lags the fantasy
    scoring period until Wednesday) keyed by team abbrev -> {kickoff_et, opponent, name}."""
    params = {"seasontype": 2}
    if week:
        params["week"] = week
    r = requests.get(SCOREBOARD_URL, params=params, timeout=15)
    r.raise_for_status()
    games = {}
    for ev in r.json().get("events", []):
        comp = ev["competitions"][0]
        kickoff = datetime.fromisoformat(comp["date"].replace("Z", "+00:00"))
        kickoff_et = kickoff.astimezone(ET)
        teams = {c["team"]["abbreviation"]: c for c in comp["competitors"]}
        for abbr, c in teams.items():
            opp = next(a for a in teams if a != abbr)
            games[abbr] = {
                "kickoff_et": kickoff_et,
                "opponent": opp,
                "name": ev.get("shortName", ""),
                "completed": comp.get("status", {}).get("type", {}).get("completed", False),
            }
    return games


def player_stats(player, scoring_period):
    """Return (projected_this_week, actual_last_week)."""
    proj = actual = None
    for st in player.get("stats", []):
        if st.get("seasonId") != SEASON:
            continue
        if st.get("scoringPeriodId") == scoring_period and st.get("statSourceId") == 1:
            proj = st.get("appliedTotal")
        if st.get("scoringPeriodId") == scoring_period - 1 and st.get("statSourceId") == 0:
            actual = st.get("appliedTotal")
    return proj, actual


def describe_entry(entry, scoring_period, games):
    p = entry["playerPoolEntry"]["player"]
    pro = PRO_TEAMS.get(p.get("proTeamId"), "?")
    g = games.get(pro)
    proj, actual = player_stats(p, scoring_period)
    locked = entry["playerPoolEntry"].get("lineupLocked", False)
    if g and (g["completed"] or datetime.now(ET) >= g["kickoff_et"]):
        locked = True
    return {
        "playerId": p["id"],
        "name": p["fullName"],
        "pos": POS_NAMES.get(p.get("defaultPositionId"), str(p.get("defaultPositionId"))),
        "proTeam": pro,
        "slot": SLOT_NAMES.get(entry["lineupSlotId"], str(entry["lineupSlotId"])),
        "slotId": entry["lineupSlotId"],
        "injury": p.get("injuryStatus") or entry.get("injuryStatus"),
        "pctOwned": round(p.get("ownership", {}).get("percentOwned", 0), 1),
        "proj": round(proj, 1) if proj is not None else None,
        "last": round(actual, 1) if actual is not None else None,
        "opp": g["opponent"] if g else None,
        "kickoff": g["kickoff_et"].strftime("%a %m/%d %I:%M%p ET") if g else None,
        "locked": locked,
    }

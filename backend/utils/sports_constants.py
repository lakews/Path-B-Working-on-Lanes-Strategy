"""
APEX TRADER - Sports Constants & Matching Utilities
====================================================

This module provides robust sport detection and team matching using:
1. Word boundary regex matching (prevents substring collisions)
2. Longest match first strategy (prevents partial matches)
3. Comprehensive sport/team coverage including Tennis

FIXES:
- BUG 1: "Seahawks" no longer matches "Hawks" (word boundary + longest first)
- BUG 5: Tennis keywords and players now supported
"""

import re
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# SPORT KEYS FOR THE ODDS API
# =============================================================================
# Maps keywords to The Odds API sport keys

SPORT_KEYS = {
    # =========================================================================
    # US SPORTS
    # =========================================================================
    'nba': 'basketball_nba',
    'basketball': 'basketball_nba',
    'nfl': 'americanfootball_nfl',
    'mlb': 'baseball_mlb',
    'baseball': 'baseball_mlb',
    'nhl': 'icehockey_nhl',
    'hockey': 'icehockey_nhl',
    
    # College
    'ncaab': 'basketball_ncaab',
    'college basketball': 'basketball_ncaab',
    'march madness': 'basketball_ncaab',
    'ncaaf': 'americanfootball_ncaaf',
    'college football': 'americanfootball_ncaaf',
    
    # =========================================================================
    # TENNIS (BUG 5 FIX)
    # =========================================================================
    'tennis': 'tennis_atp_aus_open',
    'atp': 'tennis_atp_aus_open',
    'wta': 'tennis_wta_aus_open',
    'australian open': 'tennis_atp_aus_open',
    'wimbledon': 'tennis_atp_wimbledon',
    'us open tennis': 'tennis_atp_us_open',
    'french open': 'tennis_atp_french_open',
    'roland garros': 'tennis_atp_french_open',
    
    # =========================================================================
    # SOCCER/FOOTBALL
    # =========================================================================
    'premier league': 'soccer_epl',
    'epl': 'soccer_epl',
    'la liga': 'soccer_spain_la_liga',
    'bundesliga': 'soccer_germany_bundesliga',
    'serie a': 'soccer_italy_serie_a',
    'ligue 1': 'soccer_france_ligue_one',
    'champions league': 'soccer_uefa_champs_league',
    'ucl': 'soccer_uefa_champs_league',
    'europa league': 'soccer_uefa_europa_league',
    'world cup': 'soccer_fifa_world_cup',
    'mls': 'soccer_usa_mls',
    
    # =========================================================================
    # COMBAT SPORTS
    # =========================================================================
    'ufc': 'mma_mixed_martial_arts',
    'mma': 'mma_mixed_martial_arts',
    'boxing': 'boxing_boxing',
    
    # =========================================================================
    # GOLF
    # =========================================================================
    'golf': 'golf_pga_championship',
    'pga': 'golf_pga_championship',
    'masters': 'golf_masters_tournament_winner',
    
    # =========================================================================
    # ESPORTS
    # =========================================================================
    'esports': 'esports_league_of_legends',
    'lol': 'esports_league_of_legends',
    'csgo': 'esports_csgo',
    'dota': 'esports_dota_2',
}


# =============================================================================
# TEAM DATABASE WITH SPORT ASSIGNMENTS
# =============================================================================
# Each team maps to (full_name, sport_key)
# Sorted by length (longest first) to prevent substring collisions

TEAM_DATABASE: Dict[str, Tuple[str, str]] = {
    # =========================================================================
    # NFL TEAMS (check these BEFORE NBA to avoid "hawks" collision)
    # =========================================================================
    'seattle seahawks': ('Seattle Seahawks', 'americanfootball_nfl'),
    'seahawks': ('Seattle Seahawks', 'americanfootball_nfl'),
    'new england patriots': ('New England Patriots', 'americanfootball_nfl'),
    'patriots': ('New England Patriots', 'americanfootball_nfl'),
    'pats': ('New England Patriots', 'americanfootball_nfl'),
    'kansas city chiefs': ('Kansas City Chiefs', 'americanfootball_nfl'),
    'chiefs': ('Kansas City Chiefs', 'americanfootball_nfl'),
    'philadelphia eagles': ('Philadelphia Eagles', 'americanfootball_nfl'),
    'eagles': ('Philadelphia Eagles', 'americanfootball_nfl'),
    'buffalo bills': ('Buffalo Bills', 'americanfootball_nfl'),
    'bills': ('Buffalo Bills', 'americanfootball_nfl'),
    'dallas cowboys': ('Dallas Cowboys', 'americanfootball_nfl'),
    'cowboys': ('Dallas Cowboys', 'americanfootball_nfl'),
    'baltimore ravens': ('Baltimore Ravens', 'americanfootball_nfl'),
    'ravens': ('Baltimore Ravens', 'americanfootball_nfl'),
    'cincinnati bengals': ('Cincinnati Bengals', 'americanfootball_nfl'),
    'bengals': ('Cincinnati Bengals', 'americanfootball_nfl'),
    'san francisco 49ers': ('San Francisco 49ers', 'americanfootball_nfl'),
    '49ers': ('San Francisco 49ers', 'americanfootball_nfl'),
    'niners': ('San Francisco 49ers', 'americanfootball_nfl'),
    'miami dolphins': ('Miami Dolphins', 'americanfootball_nfl'),
    'dolphins': ('Miami Dolphins', 'americanfootball_nfl'),
    'detroit lions': ('Detroit Lions', 'americanfootball_nfl'),
    'green bay packers': ('Green Bay Packers', 'americanfootball_nfl'),
    'packers': ('Green Bay Packers', 'americanfootball_nfl'),
    'new york jets': ('New York Jets', 'americanfootball_nfl'),
    'jets': ('New York Jets', 'americanfootball_nfl'),
    'new york giants': ('New York Giants', 'americanfootball_nfl'),
    'ny giants': ('New York Giants', 'americanfootball_nfl'),
    'los angeles chargers': ('Los Angeles Chargers', 'americanfootball_nfl'),
    'chargers': ('Los Angeles Chargers', 'americanfootball_nfl'),
    'los angeles rams': ('Los Angeles Rams', 'americanfootball_nfl'),
    'rams': ('Los Angeles Rams', 'americanfootball_nfl'),
    'pittsburgh steelers': ('Pittsburgh Steelers', 'americanfootball_nfl'),
    'steelers': ('Pittsburgh Steelers', 'americanfootball_nfl'),
    'denver broncos': ('Denver Broncos', 'americanfootball_nfl'),
    'broncos': ('Denver Broncos', 'americanfootball_nfl'),
    'las vegas raiders': ('Las Vegas Raiders', 'americanfootball_nfl'),
    'raiders': ('Las Vegas Raiders', 'americanfootball_nfl'),
    'arizona cardinals': ('Arizona Cardinals', 'americanfootball_nfl'),
    'atlanta falcons': ('Atlanta Falcons', 'americanfootball_nfl'),
    'falcons': ('Atlanta Falcons', 'americanfootball_nfl'),
    'carolina panthers': ('Carolina Panthers', 'americanfootball_nfl'),
    'panthers': ('Carolina Panthers', 'americanfootball_nfl'),
    'chicago bears': ('Chicago Bears', 'americanfootball_nfl'),
    'bears': ('Chicago Bears', 'americanfootball_nfl'),
    'cleveland browns': ('Cleveland Browns', 'americanfootball_nfl'),
    'browns': ('Cleveland Browns', 'americanfootball_nfl'),
    'houston texans': ('Houston Texans', 'americanfootball_nfl'),
    'texans': ('Houston Texans', 'americanfootball_nfl'),
    'indianapolis colts': ('Indianapolis Colts', 'americanfootball_nfl'),
    'colts': ('Indianapolis Colts', 'americanfootball_nfl'),
    'jacksonville jaguars': ('Jacksonville Jaguars', 'americanfootball_nfl'),
    'jaguars': ('Jacksonville Jaguars', 'americanfootball_nfl'),
    'tennessee titans': ('Tennessee Titans', 'americanfootball_nfl'),
    'titans': ('Tennessee Titans', 'americanfootball_nfl'),
    'new orleans saints': ('New Orleans Saints', 'americanfootball_nfl'),
    'saints': ('New Orleans Saints', 'americanfootball_nfl'),
    'minnesota vikings': ('Minnesota Vikings', 'americanfootball_nfl'),
    'vikings': ('Minnesota Vikings', 'americanfootball_nfl'),
    'washington commanders': ('Washington Commanders', 'americanfootball_nfl'),
    'commanders': ('Washington Commanders', 'americanfootball_nfl'),
    'tampa bay buccaneers': ('Tampa Bay Buccaneers', 'americanfootball_nfl'),
    'buccaneers': ('Tampa Bay Buccaneers', 'americanfootball_nfl'),
    'bucs': ('Tampa Bay Buccaneers', 'americanfootball_nfl'),
    
    # =========================================================================
    # NBA TEAMS
    # =========================================================================
    'los angeles lakers': ('Los Angeles Lakers', 'basketball_nba'),
    'lakers': ('Los Angeles Lakers', 'basketball_nba'),
    'boston celtics': ('Boston Celtics', 'basketball_nba'),
    'celtics': ('Boston Celtics', 'basketball_nba'),
    'golden state warriors': ('Golden State Warriors', 'basketball_nba'),
    'warriors': ('Golden State Warriors', 'basketball_nba'),
    'chicago bulls': ('Chicago Bulls', 'basketball_nba'),
    'bulls': ('Chicago Bulls', 'basketball_nba'),
    'miami heat': ('Miami Heat', 'basketball_nba'),
    'heat': ('Miami Heat', 'basketball_nba'),
    'brooklyn nets': ('Brooklyn Nets', 'basketball_nba'),
    'nets': ('Brooklyn Nets', 'basketball_nba'),
    'new york knicks': ('New York Knicks', 'basketball_nba'),
    'knicks': ('New York Knicks', 'basketball_nba'),
    'philadelphia 76ers': ('Philadelphia 76ers', 'basketball_nba'),
    'sixers': ('Philadelphia 76ers', 'basketball_nba'),
    '76ers': ('Philadelphia 76ers', 'basketball_nba'),
    'milwaukee bucks': ('Milwaukee Bucks', 'basketball_nba'),
    'bucks': ('Milwaukee Bucks', 'basketball_nba'),
    'phoenix suns': ('Phoenix Suns', 'basketball_nba'),
    'suns': ('Phoenix Suns', 'basketball_nba'),
    'dallas mavericks': ('Dallas Mavericks', 'basketball_nba'),
    'mavericks': ('Dallas Mavericks', 'basketball_nba'),
    'mavs': ('Dallas Mavericks', 'basketball_nba'),
    'denver nuggets': ('Denver Nuggets', 'basketball_nba'),
    'nuggets': ('Denver Nuggets', 'basketball_nba'),
    'la clippers': ('LA Clippers', 'basketball_nba'),
    'clippers': ('LA Clippers', 'basketball_nba'),
    'oklahoma city thunder': ('Oklahoma City Thunder', 'basketball_nba'),
    'thunder': ('Oklahoma City Thunder', 'basketball_nba'),
    'houston rockets': ('Houston Rockets', 'basketball_nba'),
    'rockets': ('Houston Rockets', 'basketball_nba'),
    'san antonio spurs': ('San Antonio Spurs', 'basketball_nba'),
    'spurs': ('San Antonio Spurs', 'basketball_nba'),
    'memphis grizzlies': ('Memphis Grizzlies', 'basketball_nba'),
    'grizzlies': ('Memphis Grizzlies', 'basketball_nba'),
    'new orleans pelicans': ('New Orleans Pelicans', 'basketball_nba'),
    'pelicans': ('New Orleans Pelicans', 'basketball_nba'),
    'minnesota timberwolves': ('Minnesota Timberwolves', 'basketball_nba'),
    'timberwolves': ('Minnesota Timberwolves', 'basketball_nba'),
    'wolves': ('Minnesota Timberwolves', 'basketball_nba'),
    'portland trail blazers': ('Portland Trail Blazers', 'basketball_nba'),
    'trail blazers': ('Portland Trail Blazers', 'basketball_nba'),
    'blazers': ('Portland Trail Blazers', 'basketball_nba'),
    'utah jazz': ('Utah Jazz', 'basketball_nba'),
    'jazz': ('Utah Jazz', 'basketball_nba'),
    'sacramento kings': ('Sacramento Kings', 'basketball_nba'),
    'kings': ('Sacramento Kings', 'basketball_nba'),
    'atlanta hawks': ('Atlanta Hawks', 'basketball_nba'),
    'hawks': ('Atlanta Hawks', 'basketball_nba'),
    'charlotte hornets': ('Charlotte Hornets', 'basketball_nba'),
    'hornets': ('Charlotte Hornets', 'basketball_nba'),
    'cleveland cavaliers': ('Cleveland Cavaliers', 'basketball_nba'),
    'cavaliers': ('Cleveland Cavaliers', 'basketball_nba'),
    'cavs': ('Cleveland Cavaliers', 'basketball_nba'),
    'detroit pistons': ('Detroit Pistons', 'basketball_nba'),
    'pistons': ('Detroit Pistons', 'basketball_nba'),
    'indiana pacers': ('Indiana Pacers', 'basketball_nba'),
    'pacers': ('Indiana Pacers', 'basketball_nba'),
    'orlando magic': ('Orlando Magic', 'basketball_nba'),
    'magic': ('Orlando Magic', 'basketball_nba'),
    'toronto raptors': ('Toronto Raptors', 'basketball_nba'),
    'raptors': ('Toronto Raptors', 'basketball_nba'),
    'washington wizards': ('Washington Wizards', 'basketball_nba'),
    'wizards': ('Washington Wizards', 'basketball_nba'),
    
    # =========================================================================
    # MLB TEAMS
    # =========================================================================
    'new york yankees': ('New York Yankees', 'baseball_mlb'),
    'yankees': ('New York Yankees', 'baseball_mlb'),
    'boston red sox': ('Boston Red Sox', 'baseball_mlb'),
    'red sox': ('Boston Red Sox', 'baseball_mlb'),
    'los angeles dodgers': ('Los Angeles Dodgers', 'baseball_mlb'),
    'dodgers': ('Los Angeles Dodgers', 'baseball_mlb'),
    'houston astros': ('Houston Astros', 'baseball_mlb'),
    'astros': ('Houston Astros', 'baseball_mlb'),
    'atlanta braves': ('Atlanta Braves', 'baseball_mlb'),
    'braves': ('Atlanta Braves', 'baseball_mlb'),
    'new york mets': ('New York Mets', 'baseball_mlb'),
    'mets': ('New York Mets', 'baseball_mlb'),
    'chicago cubs': ('Chicago Cubs', 'baseball_mlb'),
    'cubs': ('Chicago Cubs', 'baseball_mlb'),
    'chicago white sox': ('Chicago White Sox', 'baseball_mlb'),
    'white sox': ('Chicago White Sox', 'baseball_mlb'),
    'philadelphia phillies': ('Philadelphia Phillies', 'baseball_mlb'),
    'phillies': ('Philadelphia Phillies', 'baseball_mlb'),
    'san diego padres': ('San Diego Padres', 'baseball_mlb'),
    'padres': ('San Diego Padres', 'baseball_mlb'),
    'seattle mariners': ('Seattle Mariners', 'baseball_mlb'),
    'mariners': ('Seattle Mariners', 'baseball_mlb'),
    'cleveland guardians': ('Cleveland Guardians', 'baseball_mlb'),
    'guardians': ('Cleveland Guardians', 'baseball_mlb'),
    'minnesota twins': ('Minnesota Twins', 'baseball_mlb'),
    'twins': ('Minnesota Twins', 'baseball_mlb'),
    'tampa bay rays': ('Tampa Bay Rays', 'baseball_mlb'),
    'rays': ('Tampa Bay Rays', 'baseball_mlb'),
    'toronto blue jays': ('Toronto Blue Jays', 'baseball_mlb'),
    'blue jays': ('Toronto Blue Jays', 'baseball_mlb'),
    'baltimore orioles': ('Baltimore Orioles', 'baseball_mlb'),
    'orioles': ('Baltimore Orioles', 'baseball_mlb'),
    'kansas city royals': ('Kansas City Royals', 'baseball_mlb'),
    'royals': ('Kansas City Royals', 'baseball_mlb'),
    'los angeles angels': ('Los Angeles Angels', 'baseball_mlb'),
    'angels': ('Los Angeles Angels', 'baseball_mlb'),
    'oakland athletics': ('Oakland Athletics', 'baseball_mlb'),
    'athletics': ('Oakland Athletics', 'baseball_mlb'),
    'texas rangers': ('Texas Rangers', 'baseball_mlb'),
    'arizona diamondbacks': ('Arizona Diamondbacks', 'baseball_mlb'),
    'diamondbacks': ('Arizona Diamondbacks', 'baseball_mlb'),
    'dbacks': ('Arizona Diamondbacks', 'baseball_mlb'),
    'colorado rockies': ('Colorado Rockies', 'baseball_mlb'),
    'rockies': ('Colorado Rockies', 'baseball_mlb'),
    'cincinnati reds': ('Cincinnati Reds', 'baseball_mlb'),
    'reds': ('Cincinnati Reds', 'baseball_mlb'),
    'milwaukee brewers': ('Milwaukee Brewers', 'baseball_mlb'),
    'brewers': ('Milwaukee Brewers', 'baseball_mlb'),
    'pittsburgh pirates': ('Pittsburgh Pirates', 'baseball_mlb'),
    'pirates': ('Pittsburgh Pirates', 'baseball_mlb'),
    'st louis cardinals': ('St. Louis Cardinals', 'baseball_mlb'),
    'cardinals': ('St. Louis Cardinals', 'baseball_mlb'),
    'washington nationals': ('Washington Nationals', 'baseball_mlb'),
    'nationals': ('Washington Nationals', 'baseball_mlb'),
    'miami marlins': ('Miami Marlins', 'baseball_mlb'),
    'marlins': ('Miami Marlins', 'baseball_mlb'),
    'san francisco giants': ('San Francisco Giants', 'baseball_mlb'),
    'giants': ('San Francisco Giants', 'baseball_mlb'),
    
    # =========================================================================
    # NHL TEAMS
    # =========================================================================
    'toronto maple leafs': ('Toronto Maple Leafs', 'icehockey_nhl'),
    'maple leafs': ('Toronto Maple Leafs', 'icehockey_nhl'),
    'leafs': ('Toronto Maple Leafs', 'icehockey_nhl'),
    'montreal canadiens': ('Montreal Canadiens', 'icehockey_nhl'),
    'canadiens': ('Montreal Canadiens', 'icehockey_nhl'),
    'habs': ('Montreal Canadiens', 'icehockey_nhl'),
    'boston bruins': ('Boston Bruins', 'icehockey_nhl'),
    'bruins': ('Boston Bruins', 'icehockey_nhl'),
    'new york rangers': ('New York Rangers', 'icehockey_nhl'),
    'rangers': ('New York Rangers', 'icehockey_nhl'),
    'chicago blackhawks': ('Chicago Blackhawks', 'icehockey_nhl'),
    'blackhawks': ('Chicago Blackhawks', 'icehockey_nhl'),
    'detroit red wings': ('Detroit Red Wings', 'icehockey_nhl'),
    'red wings': ('Detroit Red Wings', 'icehockey_nhl'),
    
    # =========================================================================
    # TENNIS PLAYERS (BUG 5 FIX)
    # =========================================================================
    'novak djokovic': ('Novak Djokovic', 'tennis_atp_aus_open'),
    'djokovic': ('Novak Djokovic', 'tennis_atp_aus_open'),
    'carlos alcaraz': ('Carlos Alcaraz', 'tennis_atp_aus_open'),
    'alcaraz': ('Carlos Alcaraz', 'tennis_atp_aus_open'),
    'jannik sinner': ('Jannik Sinner', 'tennis_atp_aus_open'),
    'sinner': ('Jannik Sinner', 'tennis_atp_aus_open'),
    'daniil medvedev': ('Daniil Medvedev', 'tennis_atp_aus_open'),
    'medvedev': ('Daniil Medvedev', 'tennis_atp_aus_open'),
    'rafael nadal': ('Rafael Nadal', 'tennis_atp_aus_open'),
    'nadal': ('Rafael Nadal', 'tennis_atp_aus_open'),
    'roger federer': ('Roger Federer', 'tennis_atp_aus_open'),
    'federer': ('Roger Federer', 'tennis_atp_aus_open'),
    'iga swiatek': ('Iga Swiatek', 'tennis_wta_aus_open'),
    'swiatek': ('Iga Swiatek', 'tennis_wta_aus_open'),
    'coco gauff': ('Coco Gauff', 'tennis_wta_aus_open'),
    'gauff': ('Coco Gauff', 'tennis_wta_aus_open'),
    'aryna sabalenka': ('Aryna Sabalenka', 'tennis_wta_aus_open'),
    'sabalenka': ('Aryna Sabalenka', 'tennis_wta_aus_open'),
    
    # =========================================================================
    # SOCCER TEAMS
    # =========================================================================
    'manchester united': ('Manchester United', 'soccer_epl'),
    'man united': ('Manchester United', 'soccer_epl'),
    'man utd': ('Manchester United', 'soccer_epl'),
    'manchester city': ('Manchester City', 'soccer_epl'),
    'man city': ('Manchester City', 'soccer_epl'),
    'liverpool': ('Liverpool', 'soccer_epl'),
    'arsenal': ('Arsenal', 'soccer_epl'),
    'chelsea': ('Chelsea', 'soccer_epl'),
    'tottenham hotspur': ('Tottenham Hotspur', 'soccer_epl'),
    'tottenham': ('Tottenham Hotspur', 'soccer_epl'),
    'real madrid': ('Real Madrid', 'soccer_spain_la_liga'),
    'barcelona': ('Barcelona', 'soccer_spain_la_liga'),
    'barca': ('Barcelona', 'soccer_spain_la_liga'),
    'bayern munich': ('Bayern Munich', 'soccer_germany_bundesliga'),
    'bayern': ('Bayern Munich', 'soccer_germany_bundesliga'),
    'paris saint germain': ('Paris Saint-Germain', 'soccer_france_ligue_one'),
    'psg': ('Paris Saint-Germain', 'soccer_france_ligue_one'),
    'juventus': ('Juventus', 'soccer_italy_serie_a'),
    'juve': ('Juventus', 'soccer_italy_serie_a'),
    'inter milan': ('Inter Milan', 'soccer_italy_serie_a'),
    'inter': ('Inter Milan', 'soccer_italy_serie_a'),
    'ac milan': ('AC Milan', 'soccer_italy_serie_a'),
    'borussia dortmund': ('Borussia Dortmund', 'soccer_germany_bundesliga'),
    'dortmund': ('Borussia Dortmund', 'soccer_germany_bundesliga'),
    'bvb': ('Borussia Dortmund', 'soccer_germany_bundesliga'),
}


# Pre-compute sorted team list for longest-match-first strategy
_SORTED_TEAMS: List[Tuple[str, str, str]] = sorted(
    [(k, v[0], v[1]) for k, v in TEAM_DATABASE.items()],
    key=lambda x: len(x[0]),
    reverse=True
)


def match_sport_and_teams(question: str) -> Tuple[Optional[str], List[str]]:
    """
    Match sport and teams from a market question using robust matching.
    
    FIXES BUG 1 (Substring Collision):
    - Uses word boundary regex matching
    - Sorts by length (longest first) to catch "Seahawks" before "Hawks"
    
    Args:
        question: Market question text
        
    Returns:
        Tuple of (sport_key, list of matched team names)
    """
    question_lower = question.lower()
    matched_teams = []
    sport_key = None
    
    # Step 1: Check for explicit sport keywords first
    for keyword, key in sorted(SPORT_KEYS.items(), key=lambda x: len(x[0]), reverse=True):
        # Use word boundary to prevent partial matches
        pattern = r'\b' + re.escape(keyword) + r'\b'
        if re.search(pattern, question_lower, re.IGNORECASE):
            sport_key = key
            logger.debug(f"[SPORTS MATCH] Sport keyword '{keyword}' -> {key}")
            break
    
    # Step 2: Match teams using longest-first strategy with word boundaries
    for team_key, full_name, team_sport in _SORTED_TEAMS:
        # Use word boundary regex to prevent substring collisions
        # This ensures "Seahawks" doesn't match "Hawks"
        pattern = r'\b' + re.escape(team_key) + r'\b'
        
        if re.search(pattern, question_lower, re.IGNORECASE):
            if full_name not in matched_teams:
                matched_teams.append(full_name)
                
                # Use team's sport if we haven't found one yet
                if sport_key is None:
                    sport_key = team_sport
                    logger.debug(f"[SPORTS MATCH] Team '{team_key}' -> sport {team_sport}")
            
            # Stop after 2 teams
            if len(matched_teams) >= 2:
                break
    
    logger.info(f"[SPORTS MATCH] Question: '{question[:50]}...' -> Sport: {sport_key}, Teams: {matched_teams}")
    
    return sport_key, matched_teams


def detect_sport(question: str) -> Optional[str]:
    """
    Detect sport type from market question.
    
    Wrapper around match_sport_and_teams for backward compatibility.
    """
    sport_key, _ = match_sport_and_teams(question)
    return sport_key


def extract_teams(question: str) -> List[str]:
    """
    Extract team names from market question.
    
    Wrapper around match_sport_and_teams for backward compatibility.
    """
    _, teams = match_sport_and_teams(question)
    return teams


def is_sports_market(question: str) -> bool:
    """
    Check if a market question is sports-related.
    
    Uses robust matching with word boundaries.
    """
    sport_key, teams = match_sport_and_teams(question)
    
    # Also check for generic sports patterns
    sports_patterns = [
        r'\bvs\.?\b',           # "vs" or "vs."
        r'\bversus\b',          # "versus"
        r'\bo/u\b',             # Over/under
        r'\bover/under\b',
        r'\bspread\b',
        r'\bmoneyline\b',
        r'\bwill\s+\w+\s+win\b',  # "Will X win"
        r'\bwill\s+\w+\s+beat\b',  # "Will X beat"
    ]
    
    question_lower = question.lower()
    has_sports_pattern = any(re.search(p, question_lower) for p in sports_patterns)
    
    return sport_key is not None or len(teams) > 0 or has_sports_pattern

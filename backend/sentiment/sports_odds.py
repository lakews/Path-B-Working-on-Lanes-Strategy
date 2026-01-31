"""
Sports Odds Integration for APEX TRADER - Statistical Arbitrage Engine
========================================================================

Real-time sports betting odds from The Odds API to replace LLM hallucination
on sports markets with actual arbitrage-derived fair values.

ARCHITECTURE:
- Primary Truth Source for Sports Markets
- Uses "Devigging" to extract True Probability from bookmaker odds
- Strict isolation: GitHub/LLM sentiment BANNED for sports

Data Flow:
1. Polymarket sports question -> Fuzzy match to Odds API event
2. Fetch bookmaker odds -> Remove Vig to get True Probability
3. Return fair_value for use in trading decisions

API: https://the-odds-api.com/
"""

import asyncio
import aiohttp
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from cachetools import TTLCache
from rapidfuzz import fuzz, process

logger = logging.getLogger(__name__)


# =============================================================================
# TODO: SECURITY ALERT - MOVE THIS KEY TO .ENV FILE BEFORE LIVE DEPLOYMENT
# =============================================================================
# CRITICAL: This API key is hardcoded for rapid development ONLY.
# Before deploying to production, this MUST be moved to an environment variable:
#   1. Add to backend/.env: ODDS_API_KEY=your_key_here
#   2. Replace the line below with: ODDS_API_KEY = os.environ.get('ODDS_API_KEY')
#   3. Delete this comment block
# FAILURE TO DO THIS WILL EXPOSE YOUR API KEY IN VERSION CONTROL
# =============================================================================
ODDS_API_KEY = os.environ.get('ODDS_API_KEY', "4c8d0ae8cc9df5fecafca3a874cfdc4f")


# Sport key mappings for The Odds API
SPORT_KEYS = {
    # US Sports
    'nba': 'basketball_nba',
    'basketball': 'basketball_nba',
    'nfl': 'americanfootball_nfl',
    'football': 'americanfootball_nfl',
    'mlb': 'baseball_mlb',
    'baseball': 'baseball_mlb',
    'nhl': 'icehockey_nhl',
    'hockey': 'icehockey_nhl',
    
    # College Sports
    'ncaab': 'basketball_ncaab',
    'college basketball': 'basketball_ncaab',
    'ncaaf': 'americanfootball_ncaaf',
    'college football': 'americanfootball_ncaaf',
    
    # Soccer/Football
    'premier league': 'soccer_epl',
    'epl': 'soccer_epl',
    'la liga': 'soccer_spain_la_liga',
    'bundesliga': 'soccer_germany_bundesliga',
    'serie a': 'soccer_italy_serie_a',
    'ligue 1': 'soccer_france_ligue_one',
    'champions league': 'soccer_uefa_champs_league',
    'ucl': 'soccer_uefa_champs_league',
    'world cup': 'soccer_fifa_world_cup',
    'mls': 'soccer_usa_mls',
    
    # Combat Sports
    'ufc': 'mma_mixed_martial_arts',
    'mma': 'mma_mixed_martial_arts',
    'boxing': 'boxing_boxing',
    
    # Tennis
    'tennis': 'tennis_atp_french_open',  # Default to major tournament
    'atp': 'tennis_atp_french_open',
    'wta': 'tennis_wta_french_open',
    
    # Golf
    'golf': 'golf_pga_championship',
    'pga': 'golf_pga_championship',
    
    # Esports
    'esports': 'esports_league_of_legends',
    'lol': 'esports_league_of_legends',
    'csgo': 'esports_csgo',
    'dota': 'esports_dota_2',
}

# Team name aliases for fuzzy matching
TEAM_ALIASES = {
    # NBA
    'lakers': 'los angeles lakers',
    'celtics': 'boston celtics',
    'warriors': 'golden state warriors',
    'bulls': 'chicago bulls',
    'heat': 'miami heat',
    'nets': 'brooklyn nets',
    'knicks': 'new york knicks',
    'sixers': 'philadelphia 76ers',
    '76ers': 'philadelphia 76ers',
    'bucks': 'milwaukee bucks',
    'suns': 'phoenix suns',
    'mavs': 'dallas mavericks',
    'mavericks': 'dallas mavericks',
    'nuggets': 'denver nuggets',
    'clippers': 'la clippers',
    'thunder': 'oklahoma city thunder',
    'rockets': 'houston rockets',
    'spurs': 'san antonio spurs',
    'grizzlies': 'memphis grizzlies',
    'pelicans': 'new orleans pelicans',
    'timberwolves': 'minnesota timberwolves',
    'blazers': 'portland trail blazers',
    'jazz': 'utah jazz',
    'kings': 'sacramento kings',
    'hawks': 'atlanta hawks',
    'hornets': 'charlotte hornets',
    'cavaliers': 'cleveland cavaliers',
    'cavs': 'cleveland cavaliers',
    'pistons': 'detroit pistons',
    'pacers': 'indiana pacers',
    'magic': 'orlando magic',
    'raptors': 'toronto raptors',
    'wizards': 'washington wizards',
    
    # NFL
    'chiefs': 'kansas city chiefs',
    'eagles': 'philadelphia eagles',
    'bills': 'buffalo bills',
    'cowboys': 'dallas cowboys',
    'ravens': 'baltimore ravens',
    'bengals': 'cincinnati bengals',
    '49ers': 'san francisco 49ers',
    'niners': 'san francisco 49ers',
    'dolphins': 'miami dolphins',
    'lions': 'detroit lions',
    'packers': 'green bay packers',
    'jets': 'new york jets',
    'ny giants': 'new york giants',
    'chargers': 'los angeles chargers',
    'rams': 'los angeles rams',
    'seahawks': 'seattle seahawks',
    'steelers': 'pittsburgh steelers',
    'patriots': 'new england patriots',
    'pats': 'new england patriots',
    'broncos': 'denver broncos',
    'raiders': 'las vegas raiders',
    'az cardinals': 'arizona cardinals',
    'falcons': 'atlanta falcons',
    'panthers': 'carolina panthers',
    'bears': 'chicago bears',
    'browns': 'cleveland browns',
    'texans': 'houston texans',
    'colts': 'indianapolis colts',
    'jaguars': 'jacksonville jaguars',
    'titans': 'tennessee titans',
    'saints': 'new orleans saints',
    'vikings': 'minnesota vikings',
    'commanders': 'washington commanders',
    'bucs': 'tampa bay buccaneers',
    'buccaneers': 'tampa bay buccaneers',
    
    # MLB
    'yankees': 'new york yankees',
    'red sox': 'boston red sox',
    'dodgers': 'los angeles dodgers',
    'astros': 'houston astros',
    'braves': 'atlanta braves',
    'mets': 'new york mets',
    'cubs': 'chicago cubs',
    'white sox': 'chicago white sox',
    'phillies': 'philadelphia phillies',
    'padres': 'san diego padres',
    'mariners': 'seattle mariners',
    'guardians': 'cleveland guardians',
    'indians': 'cleveland guardians',  # Old name
    'twins': 'minnesota twins',
    'rays': 'tampa bay rays',
    'blue jays': 'toronto blue jays',
    'orioles': 'baltimore orioles',
    'royals': 'kansas city royals',
    'angels': 'los angeles angels',
    'athletics': 'oakland athletics',
    'rangers': 'texas rangers',
    'diamondbacks': 'arizona diamondbacks',
    'dbacks': 'arizona diamondbacks',
    'rockies': 'colorado rockies',
    'reds': 'cincinnati reds',
    'brewers': 'milwaukee brewers',
    'pirates': 'pittsburgh pirates',
    'stl cardinals': 'st louis cardinals',
    'nationals': 'washington nationals',
    'marlins': 'miami marlins',
    'sf giants': 'san francisco giants',
    
    # Soccer/Football
    'man united': 'manchester united',
    'man utd': 'manchester united',
    'man city': 'manchester city',
    'liverpool': 'liverpool',
    'arsenal': 'arsenal',
    'chelsea': 'chelsea',
    'tottenham': 'tottenham hotspur',
    'tottenham spurs': 'tottenham hotspur',
    'real madrid': 'real madrid',
    'barca': 'barcelona',
    'barcelona': 'barcelona',
    'bayern': 'bayern munich',
    'bayern munich': 'bayern munich',
    'psg': 'paris saint germain',
    'juventus': 'juventus',
    'juve': 'juventus',
    'inter': 'inter milan',
    'inter milan': 'inter milan',
    'ac milan': 'ac milan',
    'milan': 'ac milan',
    'dortmund': 'borussia dortmund',
    'bvb': 'borussia dortmund',
}


class SportsOddsAnalyzer:
    """
    Real sports odds analyzer using The Odds API.
    
    Replaces LLM hallucination with real bookmaker-derived fair values.
    Uses devigging to extract true probabilities from betting lines.
    """
    
    BASE_URL = "https://api.the-odds-api.com/v4"
    
    def __init__(self):
        # 30-minute cache to respect free tier limits (500 req/month)
        self._cache = TTLCache(maxsize=500, ttl=1800)
        self._events_cache = TTLCache(maxsize=100, ttl=1800)
        
        self._api_key = ODDS_API_KEY
        self._requests_made = 0
        self._requests_remaining = None
        self._last_request_time = None
        
        # Log free tier warning
        logger.warning(
            "WARNING: RUNNING ON FREE TIER ODDS API. "
            "DATA IS DELAYED/CACHED (30 MIN TTL). "
            "UPGRADE TO PAID TIER FOR LIVE HFT."
        )
        print(
            "\n" + "="*70 + "\n"
            "WARNING: RUNNING ON FREE TIER ODDS API.\n"
            "DATA IS DELAYED/CACHED (30 MIN TTL).\n"
            "UPGRADE TO PAID TIER FOR LIVE HFT.\n"
            + "="*70 + "\n"
        )
    
    def _detect_sport(self, question: str) -> Optional[str]:
        """Detect sport type from market question."""
        question_lower = question.lower()
        
        for keyword, sport_key in SPORT_KEYS.items():
            if keyword in question_lower:
                return sport_key
        
        # Check for team names that imply sport
        nba_teams = ['lakers', 'celtics', 'warriors', 'heat', 'nets', 'knicks', 
                     'bucks', 'suns', 'nuggets', 'clippers', 'thunder', 'rockets']
        nfl_teams = ['chiefs', 'eagles', 'bills', 'cowboys', 'ravens', 'bengals',
                     '49ers', 'dolphins', 'lions', 'packers', 'jets', 'steelers']
        mlb_teams = ['yankees', 'dodgers', 'astros', 'braves', 'mets', 'cubs',
                     'phillies', 'padres', 'mariners', 'rays', 'blue jays']
        
        for team in nba_teams:
            if team in question_lower:
                return 'basketball_nba'
        
        for team in nfl_teams:
            if team in question_lower:
                return 'americanfootball_nfl'
        
        for team in mlb_teams:
            if team in question_lower:
                return 'baseball_mlb'
        
        return None
    
    def _extract_teams(self, question: str) -> List[str]:
        """Extract team names from market question."""
        question_lower = question.lower()
        teams = []
        
        # Check for known team aliases
        for alias, full_name in TEAM_ALIASES.items():
            if alias in question_lower:
                teams.append(full_name)
        
        # Also try to extract "Team A vs Team B" pattern
        vs_patterns = [
            r'(\w+(?:\s+\w+)?)\s+(?:vs\.?|versus|v\.?|against)\s+(\w+(?:\s+\w+)?)',
            r'will\s+(?:the\s+)?(\w+(?:\s+\w+)?)\s+(?:beat|defeat|win)',
        ]
        
        for pattern in vs_patterns:
            match = re.search(pattern, question_lower)
            if match:
                for group in match.groups():
                    if group:
                        # Expand alias if found
                        expanded = TEAM_ALIASES.get(group.strip(), group.strip())
                        if expanded not in teams:
                            teams.append(expanded)
        
        return teams[:2]  # Return max 2 teams
    
    def _devig_odds(self, outcomes: List[Dict]) -> Dict[str, float]:
        """
        Remove bookmaker's vig (fee) to get true probabilities.
        
        Formula: True_Prob = Implied_Prob / Sum_of_All_Implied_Probs
        
        For American odds:
        - Negative odds (favorite): Implied_Prob = |odds| / (|odds| + 100)
        - Positive odds (underdog): Implied_Prob = 100 / (odds + 100)
        """
        if not outcomes:
            return {}
        
        implied_probs = {}
        
        for outcome in outcomes:
            name = outcome.get('name', '')
            price = outcome.get('price', 0)
            
            if price == 0:
                continue
            
            # Convert American odds to implied probability
            if price < 0:
                # Favorite: -150 means 150/(150+100) = 60%
                implied_prob = abs(price) / (abs(price) + 100)
            else:
                # Underdog: +200 means 100/(200+100) = 33.3%
                implied_prob = 100 / (price + 100)
            
            implied_probs[name] = implied_prob
        
        # Calculate total implied probability (includes vig)
        total_implied = sum(implied_probs.values())
        
        if total_implied == 0:
            return {}
        
        # Devig: normalize to remove the overround
        true_probs = {}
        for name, implied in implied_probs.items():
            true_probs[name] = implied / total_implied
        
        return true_probs
    
    def _devig_decimal_odds(self, outcomes: List[Dict]) -> Dict[str, float]:
        """
        Devig decimal odds (European format).
        
        Decimal odds: Implied_Prob = 1 / decimal_odds
        """
        if not outcomes:
            return {}
        
        implied_probs = {}
        
        for outcome in outcomes:
            name = outcome.get('name', '')
            price = outcome.get('price', 0)
            
            if price <= 1:  # Invalid decimal odds
                continue
            
            # Decimal odds to implied probability
            implied_prob = 1 / price
            implied_probs[name] = implied_prob
        
        # Calculate overround
        total_implied = sum(implied_probs.values())
        
        if total_implied == 0:
            return {}
        
        # Devig
        true_probs = {}
        for name, implied in implied_probs.items():
            true_probs[name] = implied / total_implied
        
        return true_probs
    
    async def _fetch_events(self, sport_key: str) -> List[Dict]:
        """Fetch upcoming events for a sport."""
        cache_key = f"events_{sport_key}"
        
        if cache_key in self._events_cache:
            return self._events_cache[cache_key]
        
        try:
            url = f"{self.BASE_URL}/sports/{sport_key}/events"
            params = {
                'apiKey': self._api_key,
                'dateFormat': 'iso',
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as resp:
                    # Track API usage
                    self._requests_remaining = resp.headers.get('x-requests-remaining')
                    self._requests_made += 1
                    self._last_request_time = datetime.now(timezone.utc)
                    
                    if resp.status == 200:
                        events = await resp.json()
                        self._events_cache[cache_key] = events
                        return events
                    elif resp.status == 401:
                        logger.error("Odds API: Invalid API key")
                    elif resp.status == 429:
                        logger.warning("Odds API: Rate limit exceeded")
                    else:
                        logger.warning(f"Odds API error: {resp.status}")
                    
                    return []
                    
        except asyncio.TimeoutError:
            logger.warning("Odds API timeout fetching events")
            return []
        except Exception as e:
            logger.error(f"Error fetching events: {e}")
            return []
    
    async def _fetch_odds(self, sport_key: str, event_id: str = None) -> List[Dict]:
        """Fetch odds for events in a sport."""
        cache_key = f"odds_{sport_key}_{event_id or 'all'}"
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        try:
            if event_id:
                url = f"{self.BASE_URL}/sports/{sport_key}/events/{event_id}/odds"
            else:
                url = f"{self.BASE_URL}/sports/{sport_key}/odds"
            
            params = {
                'apiKey': self._api_key,
                'regions': 'us,us2,eu',  # Multiple regions for better coverage
                'markets': 'h2h',  # Head-to-head (moneyline)
                'oddsFormat': 'american',
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as resp:
                    # Track API usage
                    self._requests_remaining = resp.headers.get('x-requests-remaining')
                    self._requests_made += 1
                    self._last_request_time = datetime.now(timezone.utc)
                    
                    if resp.status == 200:
                        odds_data = await resp.json()
                        self._cache[cache_key] = odds_data
                        return odds_data
                    elif resp.status == 429:
                        logger.warning("Odds API: Rate limit exceeded - using cached data only")
                    else:
                        logger.warning(f"Odds API odds fetch error: {resp.status}")
                    
                    return []
                    
        except asyncio.TimeoutError:
            logger.warning("Odds API timeout fetching odds")
            return []
        except Exception as e:
            logger.error(f"Error fetching odds: {e}")
            return []
    
    def _fuzzy_match_event(self, teams: List[str], events: List[Dict], threshold: int = 60) -> Optional[Dict]:
        """
        Fuzzy match extracted teams to API events.
        
        Uses rapidfuzz for fast approximate string matching.
        """
        if not teams or not events:
            return None
        
        best_match = None
        best_score = 0
        
        for event in events:
            home_team = event.get('home_team', '').lower()
            away_team = event.get('away_team', '').lower()
            
            # Create match string
            event_str = f"{home_team} {away_team}"
            query_str = ' '.join(teams)
            
            # Calculate fuzzy match score
            score = fuzz.token_set_ratio(query_str, event_str)
            
            # Also try individual team matching
            for team in teams:
                home_score = fuzz.ratio(team.lower(), home_team)
                away_score = fuzz.ratio(team.lower(), away_team)
                individual_best = max(home_score, away_score)
                score = max(score, individual_best)
            
            if score > best_score and score >= threshold:
                best_score = score
                best_match = event
        
        if best_match:
            logger.info(f"Fuzzy matched teams {teams} to event: "
                       f"{best_match.get('home_team')} vs {best_match.get('away_team')} "
                       f"(score: {best_score})")
        
        return best_match
    
    def _aggregate_bookmaker_odds(self, odds_data: Dict) -> Dict[str, float]:
        """
        Aggregate odds from multiple bookmakers for more accurate fair value.
        
        Takes the average devigged probability across all bookmakers.
        """
        all_probs = {}
        bookmaker_count = 0
        
        bookmakers = odds_data.get('bookmakers', [])
        
        for bookmaker in bookmakers:
            markets = bookmaker.get('markets', [])
            
            for market in markets:
                if market.get('key') != 'h2h':
                    continue
                
                outcomes = market.get('outcomes', [])
                devigged = self._devig_odds(outcomes)
                
                if devigged:
                    bookmaker_count += 1
                    for name, prob in devigged.items():
                        if name not in all_probs:
                            all_probs[name] = []
                        all_probs[name].append(prob)
        
        # Average across bookmakers
        fair_values = {}
        for name, probs in all_probs.items():
            fair_values[name] = sum(probs) / len(probs)
        
        logger.debug(f"Aggregated fair values from {bookmaker_count} bookmakers: {fair_values}")
        
        return fair_values
    
    def _determine_market_side(self, question: str, teams: List[str], 
                                home_team: str, away_team: str) -> Optional[str]:
        """
        Determine which side of the bet the Polymarket question is asking about.
        
        E.g., "Will the Lakers beat the Celtics?" -> Lakers
        """
        question_lower = question.lower()
        
        # Check for explicit "will X win/beat" patterns
        win_patterns = [
            r'will\s+(?:the\s+)?(\w+(?:\s+\w+)?)\s+(?:win|beat|defeat)',
            r'(\w+(?:\s+\w+)?)\s+(?:to\s+)?win',
        ]
        
        for pattern in win_patterns:
            match = re.search(pattern, question_lower)
            if match:
                subject = match.group(1).strip()
                # Expand alias
                subject = TEAM_ALIASES.get(subject, subject)
                
                # Match to home/away
                home_score = fuzz.ratio(subject, home_team.lower())
                away_score = fuzz.ratio(subject, away_team.lower())
                
                if home_score > away_score and home_score > 50:
                    return home_team
                elif away_score > home_score and away_score > 50:
                    return away_team
        
        # Fallback: first team mentioned is usually the subject
        if teams:
            first_team = teams[0]
            home_score = fuzz.ratio(first_team, home_team.lower())
            away_score = fuzz.ratio(first_team, away_team.lower())
            
            if home_score > away_score:
                return home_team
            else:
                return away_team
        
        return None
    
    async def analyze_market(self, market_data: Dict) -> Dict:
        """
        Analyze a sports market using real bookmaker odds.
        
        Args:
            market_data: Polymarket market data containing:
                - question: Market question
                - category: Should be 'sports' or similar
                - id: Market ID
        
        Returns:
            Dict containing:
                - sports_fair_value: Devigged true probability (0-1)
                - sports_confidence: Confidence in the fair value
                - matched_event: The matched sporting event
                - bookmakers_used: Number of bookmakers aggregated
                - is_sports_market: Whether this is a valid sports market
                - source: 'odds_api'
        """
        question = market_data.get('question', '')
        
        result = {
            'sports_fair_value': 0.5,
            'sports_confidence': 0.0,
            'matched_event': None,
            'bookmakers_used': 0,
            'is_sports_market': False,
            'source': 'odds_api',
            'error': None,
        }
        
        # Step 1: Detect sport type
        sport_key = self._detect_sport(question)
        if not sport_key:
            result['error'] = 'could_not_detect_sport'
            return result
        
        result['sport_detected'] = sport_key
        
        # Step 2: Extract teams from question
        teams = self._extract_teams(question)
        if not teams:
            result['error'] = 'could_not_extract_teams'
            return result
        
        result['teams_extracted'] = teams
        
        # Step 3: Fetch events and odds
        try:
            odds_data = await self._fetch_odds(sport_key)
            
            if not odds_data:
                result['error'] = 'no_odds_data'
                return result
            
            # Step 4: Fuzzy match to find the right event
            matched_event = self._fuzzy_match_event(teams, odds_data)
            
            if not matched_event:
                result['error'] = 'no_matching_event'
                return result
            
            result['matched_event'] = {
                'id': matched_event.get('id'),
                'home_team': matched_event.get('home_team'),
                'away_team': matched_event.get('away_team'),
                'commence_time': matched_event.get('commence_time'),
            }
            result['is_sports_market'] = True
            
            # Step 5: Aggregate and devig odds
            fair_values = self._aggregate_bookmaker_odds(matched_event)
            
            if not fair_values:
                result['error'] = 'could_not_devig_odds'
                return result
            
            result['bookmakers_used'] = len(matched_event.get('bookmakers', []))
            
            # Step 6: Determine which side the question is asking about
            home_team = matched_event.get('home_team', '')
            away_team = matched_event.get('away_team', '')
            
            market_subject = self._determine_market_side(question, teams, home_team, away_team)
            
            if market_subject and market_subject in fair_values:
                result['sports_fair_value'] = fair_values[market_subject]
                result['market_subject'] = market_subject
            elif home_team in fair_values:
                # Default to home team if can't determine
                result['sports_fair_value'] = fair_values[home_team]
                result['market_subject'] = home_team
            else:
                # Use first available
                first_team = list(fair_values.keys())[0]
                result['sports_fair_value'] = fair_values[first_team]
                result['market_subject'] = first_team
            
            result['all_fair_values'] = fair_values
            
            # Confidence based on bookmaker count and match quality
            bookmaker_confidence = min(0.9, result['bookmakers_used'] / 10)
            result['sports_confidence'] = bookmaker_confidence
            
            logger.info(f"Sports odds for '{question[:50]}...': "
                       f"fair_value={result['sports_fair_value']:.3f}, "
                       f"subject={result.get('market_subject')}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing sports market: {e}")
            result['error'] = str(e)
            return result
    
    def get_api_stats(self) -> Dict:
        """Get API usage statistics."""
        return {
            'requests_made': self._requests_made,
            'requests_remaining': self._requests_remaining,
            'last_request': self._last_request_time.isoformat() if self._last_request_time else None,
            'cache_size': len(self._cache),
            'events_cache_size': len(self._events_cache),
            'cache_ttl_seconds': 1800,
            'tier': 'FREE',
            'monthly_limit': 500,
        }


# Singleton instance
_sports_odds_analyzer: Optional[SportsOddsAnalyzer] = None


def get_sports_odds_analyzer() -> SportsOddsAnalyzer:
    """Get singleton instance of sports odds analyzer."""
    global _sports_odds_analyzer
    if _sports_odds_analyzer is None:
        _sports_odds_analyzer = SportsOddsAnalyzer()
    return _sports_odds_analyzer

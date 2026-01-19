"""
GitHub Sentiment Analysis for Crypto/Tech Markets

Extracts sentiment signals from GitHub activity:
1. Commit Velocity - Development pace
2. Release Activity - Milestones shipped
3. Issue Sentiment - Bug vs feature ratio
4. Star/Fork Trend - Community interest
5. PR Activity - Development health
6. Contributor Growth - Project health

Useful for: Crypto markets, blockchain upgrades, tech predictions
"""

import os
import asyncio
import aiohttp
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


# Map market keywords to GitHub repos
MARKET_REPO_MAP = {
    # Major Cryptocurrencies
    "ethereum": ["ethereum/go-ethereum", "ethereum/solidity", "ethereum/EIPs"],
    "bitcoin": ["bitcoin/bitcoin", "bitcoin/bips"],
    "solana": ["solana-labs/solana", "solana-labs/solana-program-library"],
    "cardano": ["input-output-hk/cardano-node"],
    "polkadot": ["paritytech/polkadot-sdk"],
    "avalanche": ["ava-labs/avalanchego"],
    "polygon": ["maticnetwork/bor", "0xPolygon/polygon-edge"],
    "arbitrum": ["OffchainLabs/nitro", "OffchainLabs/arbitrum"],
    "optimism": ["ethereum-optimism/optimism"],
    "base": ["base-org/node"],
    
    # DeFi Protocols
    "uniswap": ["Uniswap/v3-core", "Uniswap/v4-core"],
    "aave": ["aave/aave-v3-core"],
    "compound": ["compound-finance/compound-protocol"],
    "makerdao": ["makerdao/dss"],
    "curve": ["curvefi/curve-contract"],
    "lido": ["lidofinance/lido-dao"],
    
    # Layer 2 & Scaling
    "zksync": ["matter-labs/zksync-era"],
    "starknet": ["starkware-libs/cairo"],
    "linea": ["Consensys/linea-monorepo"],
    
    # Infrastructure
    "chainlink": ["smartcontractkit/chainlink"],
    "thegraph": ["graphprotocol/graph-node"],
    
    # Upgrade-specific keywords
    "pectra": ["ethereum/go-ethereum", "ethereum/EIPs"],
    "dencun": ["ethereum/go-ethereum", "ethereum/EIPs"],
    "cancun": ["ethereum/go-ethereum"],
    "shanghai": ["ethereum/go-ethereum"],
    "taproot": ["bitcoin/bitcoin"],
    
    # General blockchain
    "blockchain": ["ethereum/go-ethereum", "bitcoin/bitcoin"],
    "defi": ["Uniswap/v3-core", "aave/aave-v3-core"],
    "nft": ["OpenZeppelin/openzeppelin-contracts"],
}


class GitHubSentimentAnalyzer:
    """
    Analyze GitHub activity for market sentiment signals.
    """
    
    BASE_URL = "https://api.github.com"
    
    def __init__(self):
        self.token = os.environ.get('GITHUB_TOKEN')
        self._cache: Dict[str, Dict] = {}
        self._cache_ttl = 300  # 5 minute cache
        self._rate_limit_remaining = 5000
        self._rate_limit_reset = None
        
        if self.token:
            logger.info("GitHub sentiment analyzer initialized with token")
        else:
            logger.warning("GitHub sentiment analyzer: No token - limited to 60 req/hour")
    
    def _get_headers(self) -> Dict:
        """Get headers for GitHub API requests."""
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "ApexTrader-Sentiment/1.0"
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers
    
    def _find_repos_for_market(self, market_question: str) -> List[str]:
        """Find relevant GitHub repos based on market question."""
        question_lower = market_question.lower()
        matched_repos = set()
        
        for keyword, repos in MARKET_REPO_MAP.items():
            if keyword in question_lower:
                matched_repos.update(repos)
        
        return list(matched_repos)[:5]  # Limit to 5 repos max
    
    async def analyze_market(self, market_data: Dict) -> Dict:
        """
        Analyze GitHub activity for a market.
        
        Returns:
        {
            'github_sentiment': float (0-1),
            'github_confidence': float (0-1),
            'signals': {
                'commit_velocity': {...},
                'release_activity': {...},
                'issue_health': {...},
                'community_trend': {...},
            },
            'repos_analyzed': [...],
            'is_relevant': bool
        }
        """
        question = market_data.get('question', '')
        market_id = market_data.get('id', '')
        category = market_data.get('category', '').lower()
        
        # Check cache
        cache_key = f"{market_id}:{question[:50]}"
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if datetime.now(timezone.utc).timestamp() - cached['timestamp'] < self._cache_ttl:
                return cached['data']
        
        # Only analyze crypto/tech markets
        is_relevant = (
            category in ['crypto', 'technology', 'science'] or
            any(kw in question.lower() for kw in MARKET_REPO_MAP.keys())
        )
        
        if not is_relevant:
            return {
                'github_sentiment': 0.5,
                'github_confidence': 0.0,
                'is_relevant': False,
                'reason': 'Market not crypto/tech related'
            }
        
        # Find relevant repos
        repos = self._find_repos_for_market(question)
        
        if not repos:
            return {
                'github_sentiment': 0.5,
                'github_confidence': 0.0,
                'is_relevant': False,
                'reason': 'No matching repos found'
            }
        
        # Analyze repos
        try:
            async with aiohttp.ClientSession() as session:
                repo_signals = []
                
                for repo in repos:
                    try:
                        signals = await self._analyze_repo(session, repo)
                        if signals:
                            repo_signals.append(signals)
                    except Exception as e:
                        logger.debug(f"Error analyzing {repo}: {e}")
                        continue
                
                if not repo_signals:
                    return {
                        'github_sentiment': 0.5,
                        'github_confidence': 0.0,
                        'is_relevant': True,
                        'reason': 'Could not fetch repo data'
                    }
                
                # Aggregate signals
                result = self._aggregate_signals(repo_signals, repos)
                
                # Cache result
                self._cache[cache_key] = {
                    'timestamp': datetime.now(timezone.utc).timestamp(),
                    'data': result
                }
                
                return result
                
        except Exception as e:
            logger.error(f"GitHub sentiment error: {e}")
            return {
                'github_sentiment': 0.5,
                'github_confidence': 0.0,
                'error': str(e)
            }
    
    async def _analyze_repo(self, session: aiohttp.ClientSession, repo: str) -> Optional[Dict]:
        """Analyze a single repository."""
        headers = self._get_headers()
        
        try:
            # Fetch repo info, commits, releases, issues in parallel
            async with asyncio.TaskGroup() as tg:
                repo_task = tg.create_task(self._fetch_repo_info(session, repo, headers))
                commits_task = tg.create_task(self._fetch_commits(session, repo, headers))
                releases_task = tg.create_task(self._fetch_releases(session, repo, headers))
                issues_task = tg.create_task(self._fetch_issues(session, repo, headers))
            
            repo_info = repo_task.result()
            commits = commits_task.result()
            releases = releases_task.result()
            issues = issues_task.result()
            
            if not repo_info:
                return None
            
            return {
                'repo': repo,
                'repo_info': repo_info,
                'commits': commits,
                'releases': releases,
                'issues': issues,
                'signals': self._calculate_repo_signals(repo_info, commits, releases, issues)
            }
            
        except Exception as e:
            logger.debug(f"Error fetching {repo}: {e}")
            return None
    
    async def _fetch_repo_info(self, session: aiohttp.ClientSession, repo: str, headers: Dict) -> Optional[Dict]:
        """Fetch basic repository info."""
        try:
            url = f"{self.BASE_URL}/repos/{repo}"
            async with session.get(url, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        'stars': data.get('stargazers_count', 0),
                        'forks': data.get('forks_count', 0),
                        'watchers': data.get('subscribers_count', 0),
                        'open_issues': data.get('open_issues_count', 0),
                        'updated_at': data.get('updated_at'),
                        'pushed_at': data.get('pushed_at'),
                    }
                return None
        except:
            return None
    
    async def _fetch_commits(self, session: aiohttp.ClientSession, repo: str, headers: Dict) -> List[Dict]:
        """Fetch recent commits."""
        try:
            # Get commits from last 7 days
            since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            url = f"{self.BASE_URL}/repos/{repo}/commits"
            params = {"since": since, "per_page": 100}
            
            async with session.get(url, headers=headers, params=params, timeout=10) as resp:
                if resp.status == 200:
                    commits = await resp.json()
                    return [
                        {
                            'date': c.get('commit', {}).get('author', {}).get('date'),
                            'message': c.get('commit', {}).get('message', '')[:100],
                            'author': c.get('author', {}).get('login') if c.get('author') else None
                        }
                        for c in commits[:100]
                    ]
                return []
        except:
            return []
    
    async def _fetch_releases(self, session: aiohttp.ClientSession, repo: str, headers: Dict) -> List[Dict]:
        """Fetch recent releases."""
        try:
            url = f"{self.BASE_URL}/repos/{repo}/releases"
            params = {"per_page": 10}
            
            async with session.get(url, headers=headers, params=params, timeout=10) as resp:
                if resp.status == 200:
                    releases = await resp.json()
                    return [
                        {
                            'tag': r.get('tag_name'),
                            'name': r.get('name'),
                            'date': r.get('published_at'),
                            'prerelease': r.get('prerelease', False),
                        }
                        for r in releases[:10]
                    ]
                return []
        except:
            return []
    
    async def _fetch_issues(self, session: aiohttp.ClientSession, repo: str, headers: Dict) -> Dict:
        """Fetch issue statistics."""
        try:
            # Get recent issues
            since = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
            url = f"{self.BASE_URL}/repos/{repo}/issues"
            params = {"since": since, "state": "all", "per_page": 100}
            
            async with session.get(url, headers=headers, params=params, timeout=10) as resp:
                if resp.status == 200:
                    issues = await resp.json()
                    
                    # Categorize issues
                    bugs = 0
                    features = 0
                    open_count = 0
                    closed_count = 0
                    
                    for issue in issues:
                        if issue.get('pull_request'):
                            continue  # Skip PRs
                        
                        labels = [l.get('name', '').lower() for l in issue.get('labels', [])]
                        title = issue.get('title', '').lower()
                        
                        if issue.get('state') == 'open':
                            open_count += 1
                        else:
                            closed_count += 1
                        
                        if any(b in labels or b in title for b in ['bug', 'error', 'fix', 'broken']):
                            bugs += 1
                        elif any(f in labels or f in title for f in ['feature', 'enhancement', 'improvement']):
                            features += 1
                    
                    return {
                        'total': len([i for i in issues if not i.get('pull_request')]),
                        'open': open_count,
                        'closed': closed_count,
                        'bugs': bugs,
                        'features': features,
                    }
                return {}
        except:
            return {}
    
    def _calculate_repo_signals(
        self, 
        repo_info: Dict, 
        commits: List, 
        releases: List, 
        issues: Dict
    ) -> Dict:
        """Calculate sentiment signals for a single repo."""
        now = datetime.now(timezone.utc)
        
        # 1. Commit Velocity (commits per day in last 7 days)
        commit_count = len(commits)
        commits_per_day = commit_count / 7
        
        # Score: 0-1 commits/day = 0.3, 1-5 = 0.5, 5-10 = 0.7, 10+ = 0.9
        if commits_per_day >= 10:
            commit_score = 0.85
        elif commits_per_day >= 5:
            commit_score = 0.70
        elif commits_per_day >= 1:
            commit_score = 0.55
        else:
            commit_score = 0.35
        
        # 2. Release Activity
        recent_releases = [
            r for r in releases
            if r.get('date') and 
            (now - datetime.fromisoformat(r['date'].replace('Z', '+00:00'))).days <= 30
        ]
        
        if len(recent_releases) >= 2:
            release_score = 0.80  # Multiple releases = very active
        elif len(recent_releases) == 1:
            release_score = 0.65
        elif releases:
            release_score = 0.50  # Has releases but not recent
        else:
            release_score = 0.40
        
        # 3. Issue Health (features vs bugs ratio)
        total_issues = issues.get('total', 0)
        bugs = issues.get('bugs', 0)
        features = issues.get('features', 0)
        closed = issues.get('closed', 0)
        
        if total_issues > 0:
            # More features than bugs = bullish
            if features > bugs:
                issue_score = 0.65
            elif bugs > features * 2:
                issue_score = 0.35  # Too many bugs = bearish
            else:
                issue_score = 0.50
            
            # Bonus for good close rate
            close_rate = closed / total_issues if total_issues > 0 else 0
            if close_rate > 0.5:
                issue_score = min(0.80, issue_score + 0.1)
        else:
            issue_score = 0.50
        
        # 4. Community Trend (stars, forks as proxy)
        stars = repo_info.get('stars', 0)
        forks = repo_info.get('forks', 0)
        
        # Large projects with high activity = healthy
        if stars > 10000:
            community_score = 0.70
        elif stars > 1000:
            community_score = 0.60
        elif stars > 100:
            community_score = 0.50
        else:
            community_score = 0.40
        
        # 5. Recency (how recently was code pushed)
        pushed_at = repo_info.get('pushed_at')
        if pushed_at:
            try:
                last_push = datetime.fromisoformat(pushed_at.replace('Z', '+00:00'))
                days_since_push = (now - last_push).days
                
                if days_since_push <= 1:
                    recency_score = 0.80
                elif days_since_push <= 7:
                    recency_score = 0.65
                elif days_since_push <= 30:
                    recency_score = 0.50
                else:
                    recency_score = 0.35
            except:
                recency_score = 0.50
        else:
            recency_score = 0.50
        
        return {
            'commit_velocity': {
                'score': commit_score,
                'commits_7d': commit_count,
                'per_day': round(commits_per_day, 2)
            },
            'release_activity': {
                'score': release_score,
                'recent_releases': len(recent_releases),
                'total_releases': len(releases)
            },
            'issue_health': {
                'score': issue_score,
                'bugs': bugs,
                'features': features,
                'close_rate': round(closed / total_issues, 2) if total_issues > 0 else 0
            },
            'community': {
                'score': community_score,
                'stars': stars,
                'forks': forks
            },
            'recency': {
                'score': recency_score,
                'last_push': pushed_at
            }
        }
    
    def _aggregate_signals(self, repo_signals: List[Dict], repos: List[str]) -> Dict:
        """Aggregate signals from multiple repos into final sentiment."""
        if not repo_signals:
            return {
                'github_sentiment': 0.5,
                'github_confidence': 0.0,
                'is_relevant': True,
                'reason': 'No repo data'
            }
        
        # Weight signals by repo importance (stars)
        weighted_scores = defaultdict(list)
        total_weight = 0
        
        for rs in repo_signals:
            signals = rs.get('signals', {})
            stars = rs.get('repo_info', {}).get('stars', 100)
            weight = min(1.0, stars / 10000)  # Cap weight at 1.0
            
            for signal_name, signal_data in signals.items():
                if isinstance(signal_data, dict) and 'score' in signal_data:
                    weighted_scores[signal_name].append({
                        'score': signal_data['score'],
                        'weight': weight,
                        'data': signal_data
                    })
            
            total_weight += weight
        
        # Calculate weighted average for each signal type
        signal_weights = {
            'commit_velocity': 0.30,
            'release_activity': 0.25,
            'issue_health': 0.15,
            'community': 0.15,
            'recency': 0.15
        }
        
        final_signals = {}
        combined_score = 0.0
        
        for signal_name, scores in weighted_scores.items():
            if scores:
                # Weighted average within signal type
                total_sw = sum(s['weight'] for s in scores)
                avg_score = sum(s['score'] * s['weight'] for s in scores) / total_sw if total_sw > 0 else 0.5
                
                final_signals[signal_name] = {
                    'score': round(avg_score, 4),
                    'repos_contributing': len(scores),
                    'details': scores[0]['data'] if len(scores) == 1 else None
                }
                
                combined_score += avg_score * signal_weights.get(signal_name, 0.1)
        
        # Normalize combined score
        combined_score = max(0.1, min(0.9, combined_score))
        
        # Confidence based on data quality
        confidence = min(0.8, 0.3 + (len(repo_signals) * 0.15) + (total_weight * 0.1))
        
        return {
            'github_sentiment': round(combined_score, 4),
            'github_confidence': round(confidence, 4),
            'is_relevant': True,
            'signals': final_signals,
            'repos_analyzed': [rs['repo'] for rs in repo_signals],
            'interpretation': self._interpret_sentiment(combined_score)
        }
    
    def _interpret_sentiment(self, score: float) -> str:
        """Generate human-readable interpretation."""
        if score >= 0.70:
            return "Strong development activity - Bullish signal"
        elif score >= 0.60:
            return "Healthy development pace - Moderately bullish"
        elif score >= 0.50:
            return "Normal activity levels - Neutral"
        elif score >= 0.40:
            return "Below average activity - Slightly bearish"
        else:
            return "Low development activity - Bearish signal"


# Singleton instance
_github_analyzer: Optional[GitHubSentimentAnalyzer] = None


def get_github_sentiment_analyzer() -> GitHubSentimentAnalyzer:
    """Get singleton GitHub sentiment analyzer instance."""
    global _github_analyzer
    if _github_analyzer is None:
        _github_analyzer = GitHubSentimentAnalyzer()
    return _github_analyzer

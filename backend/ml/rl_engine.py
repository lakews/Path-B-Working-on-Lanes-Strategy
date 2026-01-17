"""
Reinforcement Learning Adaptive Strategy Engine
Uses Deep Q-Network (DQN) with Prioritized Experience Replay
Architecture: 2 hidden layers, 64 neurons each
"""
import numpy as np
import logging
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timezone
from database import get_db
from config import config
import uuid
import json
import os

# Import DQN components
from ml.dqn import DQNAgent, device

logger = logging.getLogger(__name__)


class RLAdaptiveEngine:
    """
    Reinforcement Learning engine for adaptive trading strategy optimization
    Now powered by Deep Q-Network (DQN) with Prioritized Experience Replay
    """
    
    def __init__(self, use_dqn: bool = True):
        self.db = get_db()
        self.use_dqn = use_dqn
        
        # State space dimensions
        self.state_features = [
            'price', 'volatility', 'sentiment', 'sharp_alignment',
            'liquidity', 'volume', 'time_to_expiry', 'portfolio_exposure'
        ]
        self.n_states = len(self.state_features)
        
        # Action space: [WAIT, BUY_SMALL, BUY_MEDIUM, BUY_LARGE, SELL_SMALL, SELL_MEDIUM, SELL_LARGE]
        self.actions = ['WAIT', 'BUY_SMALL', 'BUY_MEDIUM', 'BUY_LARGE', 'SELL_SMALL', 'SELL_MEDIUM', 'SELL_LARGE']
        self.n_actions = len(self.actions)
        
        # Initialize DQN Agent
        if self.use_dqn:
            self.dqn_agent = DQNAgent(
                state_size=self.n_states,
                action_size=self.n_actions,
                hidden_size=64,  # Simple architecture
                learning_rate=0.001,
                gamma=0.95,
                epsilon=0.15,
                epsilon_decay=0.995,
                epsilon_min=0.05,
                buffer_size=10000,
                batch_size=32,
                target_update_freq=100
            )
            logger.info("RL Engine initialized with DQN + Prioritized Experience Replay")
        else:
            self.dqn_agent = None
            logger.info("RL Engine initialized with Q-table (legacy mode)")
        
        # Legacy Q-Table (kept as fallback)
        self.state_bins = 10
        self.q_table = np.zeros((self.state_bins ** 4, self.n_actions))
        
        # Learning parameters (for legacy mode)
        self.learning_rate = 0.1
        self.discount_factor = 0.95
        self.epsilon = 0.15
        self.epsilon_decay = 0.995
        self.min_epsilon = 0.05
        
        # Legacy experience replay buffer
        self.replay_buffer: List[Dict] = []
        self.max_buffer_size = 10000
        self.batch_size = 32
        
        # Performance tracking
        self.episode_rewards: List[float] = []
        self.training_iterations = 0
        
        # Pending actions store (for reward assignment)
        self._pending_states: Dict[str, Tuple[np.ndarray, int]] = {}
    
    async def get_optimal_action(self, market_data: Dict, signals: Dict) -> Tuple[str, float]:
        """
        Get optimal action using trained DQN policy
        Returns: (action, confidence)
        """
        try:
            # Build state representation
            state = self._build_state(market_data, signals)
            
            if self.use_dqn and self.dqn_agent:
                # Use DQN for action selection
                action_idx, confidence = self.dqn_agent.select_action(state)
            else:
                # Legacy Q-table mode
                state_idx = self._discretize_state(state)
                
                if np.random.random() < self.epsilon:
                    action_idx = np.random.randint(self.n_actions)
                    confidence = 0.5
                else:
                    q_values = self.q_table[state_idx]
                    action_idx = np.argmax(q_values)
                    confidence = self._softmax_confidence(q_values, action_idx)
            
            action = self.actions[action_idx]
            
            # Store state for later reward assignment
            market_id = market_data.get('market_id') or market_data.get('id')
            self._pending_states[market_id] = (state.copy(), action_idx)
            await self._store_pending_action(market_id, state, action_idx)
            
            logger.info(f"RL Action: {action} (confidence: {confidence:.2f}, epsilon: {self._get_epsilon():.3f})")
            
            return action, confidence
            
        except Exception as e:
            logger.error(f"Error getting optimal action: {e}")
            return 'WAIT', 0.0
    
    def _get_epsilon(self) -> float:
        """Get current epsilon value"""
        if self.use_dqn and self.dqn_agent:
            return self.dqn_agent.epsilon
        return self.epsilon
    
    def _build_state(self, market_data: Dict, signals: Dict) -> np.ndarray:
        """Build state vector from market data and signals"""
        try:
            state = np.array([
                market_data.get('yes_price', 0.5),
                signals.get('volatility', 0.5),
                signals.get('sentiment', 0.5),
                signals.get('sharp_alignment', 0.5),
                min(market_data.get('liquidity', 0) / 100000, 1.0),
                min(market_data.get('volume', 0) / 50000, 1.0),
                self._calculate_time_to_expiry(market_data),
                self._get_portfolio_exposure()
            ], dtype=np.float32)
            return state
        except Exception as e:
            logger.error(f"Error building state: {e}")
            return np.zeros(self.n_states, dtype=np.float32)
    
    def _discretize_state(self, state: np.ndarray) -> int:
        """Discretize continuous state to index (for legacy Q-table)"""
        try:
            key_features = state[:4]
            bins = np.digitize(key_features, np.linspace(0, 1, self.state_bins))
            
            idx = 0
            for i, b in enumerate(bins):
                idx += b * (self.state_bins ** i)
            
            return min(idx, self.q_table.shape[0] - 1)
        except Exception as e:
            logger.error(f"Error discretizing state: {e}")
            return 0
    
    def _softmax_confidence(self, q_values: np.ndarray, action_idx: int) -> float:
        """Calculate softmax confidence for selected action"""
        try:
            exp_q = np.exp(q_values - np.max(q_values))
            softmax = exp_q / np.sum(exp_q)
            return float(softmax[action_idx])
        except Exception as e:
            logger.error(f"Error calculating softmax: {e}")
            return 0.5
    
    def _calculate_time_to_expiry(self, market_data: Dict) -> float:
        """Calculate normalized time to market expiry"""
        try:
            end_date = market_data.get('end_date')
            if not end_date:
                return 1.0
            
            if isinstance(end_date, str):
                end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            
            now = datetime.now(timezone.utc)
            time_remaining = (end_date - now).total_seconds()
            
            normalized = min(max(time_remaining / (30 * 24 * 3600), 0), 1)
            return normalized
        except Exception:
            return 1.0
    
    def _get_portfolio_exposure(self) -> float:
        """Get current portfolio exposure as normalized value"""
        try:
            return 0.5
        except Exception:
            return 0.5
    
    async def update_from_reward(self, market_id: str, reward: float, next_market_data: Optional[Dict] = None, done: bool = False):
        """
        Update DQN based on received reward
        For DQN: stores experience and triggers training step
        For legacy: updates Q-table directly
        """
        try:
            # Get pending action for this market
            if market_id in self._pending_states:
                state, action_idx = self._pending_states[market_id]
                del self._pending_states[market_id]
            else:
                pending = await self.db.rl_pending_actions.find_one(
                    {"market_id": market_id},
                    sort=[("timestamp", -1)]
                )
                
                if not pending:
                    return
                
                state = np.array(pending.get('state', []), dtype=np.float32)
                action_idx = pending.get('action_idx', 0)
            
            # Build next state
            if next_market_data:
                next_state = self._build_state(next_market_data, {})
            else:
                next_state = state.copy()  # Same state if not provided
            
            if self.use_dqn and self.dqn_agent:
                # Store experience in prioritized replay buffer
                self.dqn_agent.store_experience(state, action_idx, reward, next_state, done)
                
                # Perform training step
                loss = self.dqn_agent.train_step()
                
                if loss is not None:
                    logger.info(f"DQN Update: reward={reward:.4f}, loss={loss:.6f}, epsilon={self.dqn_agent.epsilon:.4f}")
                else:
                    logger.info(f"DQN Experience stored: reward={reward:.4f}")
                
                self.training_iterations = self.dqn_agent.training_iterations
            else:
                # Legacy Q-table update
                state_idx = self._discretize_state(state)
                current_q = self.q_table[state_idx, action_idx]
                
                max_next_q = np.max(self.q_table[state_idx])
                new_q = current_q + self.learning_rate * (
                    reward + self.discount_factor * max_next_q - current_q
                )
                
                self.q_table[state_idx, action_idx] = new_q
                
                # Add to replay buffer
                experience = {
                    'state': state.tolist(),
                    'action': action_idx,
                    'reward': reward,
                    'next_state': next_state.tolist(),
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
                self.replay_buffer.append(experience)
                
                if len(self.replay_buffer) > self.max_buffer_size:
                    self.replay_buffer.pop(0)
                
                self.epsilon = max(self.min_epsilon, self.epsilon * self.epsilon_decay)
                self.training_iterations += 1
                
                logger.info(f"Q-Table Update: reward={reward:.4f}, new_q={new_q:.4f}, epsilon={self.epsilon:.4f}")
            
            self.episode_rewards.append(reward)
            await self._store_training_progress(reward)
            
        except Exception as e:
            logger.error(f"Error updating from reward: {e}")
    
    async def train_from_replay(self):
        """Train on batch from experience replay buffer"""
        try:
            if self.use_dqn and self.dqn_agent:
                # DQN training step (uses prioritized replay internally)
                for _ in range(5):  # Multiple training steps
                    loss = self.dqn_agent.train_step()
                    if loss is not None:
                        logger.debug(f"DQN batch training loss: {loss:.6f}")
                
                logger.info("DQN batch training completed")
            else:
                # Legacy Q-table replay training
                if len(self.replay_buffer) < self.batch_size:
                    return
                
                indices = np.random.choice(len(self.replay_buffer), self.batch_size, replace=False)
                batch = [self.replay_buffer[i] for i in indices]
                
                for experience in batch:
                    state = np.array(experience['state'])
                    action = experience['action']
                    reward = experience['reward']
                    next_state = np.array(experience['next_state'])
                    
                    state_idx = self._discretize_state(state)
                    next_state_idx = self._discretize_state(next_state)
                    
                    current_q = self.q_table[state_idx, action]
                    max_next_q = np.max(self.q_table[next_state_idx])
                    
                    new_q = current_q + self.learning_rate * (
                        reward + self.discount_factor * max_next_q - current_q
                    )
                    
                    self.q_table[state_idx, action] = new_q
                
                logger.info(f"Q-table batch training completed: {self.batch_size} experiences")
            
        except Exception as e:
            logger.error(f"Error in replay training: {e}")
    
    async def _store_pending_action(self, market_id: str, state: np.ndarray, action_idx: int):
        """Store pending action for later reward assignment"""
        try:
            await self.db.rl_pending_actions.insert_one({
                "id": str(uuid.uuid4()),
                "market_id": market_id,
                "state": state.tolist(),
                "action_idx": int(action_idx),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        except Exception as e:
            logger.error(f"Error storing pending action: {e}")
    
    async def _store_training_progress(self, reward: float):
        """Store training progress metrics"""
        try:
            if self.training_iterations % 100 == 0:
                avg_reward = np.mean(self.episode_rewards[-100:]) if self.episode_rewards else 0
                
                progress_data = {
                    "id": str(uuid.uuid4()),
                    "iteration": self.training_iterations,
                    "epsilon": self._get_epsilon(),
                    "avg_reward_100": avg_reward,
                    "buffer_size": len(self.dqn_agent.memory) if self.use_dqn and self.dqn_agent else len(self.replay_buffer),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "model_type": "DQN" if self.use_dqn else "Q-table"
                }
                
                await self.db.rl_training_progress.insert_one(progress_data)
        except Exception as e:
            logger.error(f"Error storing training progress: {e}")
    
    async def get_training_stats(self) -> Dict:
        """Get current training statistics with detailed performance metrics"""
        try:
            if self.use_dqn and self.dqn_agent:
                # Get DQN stats
                dqn_stats = self.dqn_agent.get_stats()
                
                # Add action distribution
                action_counts = {action: 0 for action in self.actions}
                
                return {
                    **dqn_stats,
                    "model_type": "DQN",
                    "prioritized_replay": True,
                    "device": str(device),
                    "action_distribution": action_counts,
                    "state_features": self.state_features
                }
            else:
                # Legacy Q-table stats
                recent_rewards = self.episode_rewards[-100:] if self.episode_rewards else []
                
                positive_rewards = [r for r in recent_rewards if r > 0]
                negative_rewards = [r for r in recent_rewards if r < 0]
                
                q_values_flat = self.q_table.flatten()
                nonzero_q = q_values_flat[q_values_flat != 0]
                
                best_actions = np.argmax(self.q_table, axis=1)
                action_counts = {action: int(np.sum(best_actions == i)) for i, action in enumerate(self.actions)}
                
                return {
                    "model_type": "Q-table",
                    "prioritized_replay": False,
                    "total_iterations": self.training_iterations,
                    "epsilon": float(self.epsilon),
                    "avg_reward_100": float(np.mean(recent_rewards)) if recent_rewards else 0,
                    "max_reward_100": float(max(recent_rewards)) if recent_rewards else 0,
                    "min_reward_100": float(min(recent_rewards)) if recent_rewards else 0,
                    "std_reward_100": float(np.std(recent_rewards)) if len(recent_rewards) > 1 else 0,
                    "positive_rate": float(len(positive_rewards) / len(recent_rewards)) if recent_rewards else 0,
                    "avg_positive_reward": float(np.mean(positive_rewards)) if positive_rewards else 0,
                    "avg_negative_reward": float(np.mean(negative_rewards)) if negative_rewards else 0,
                    "buffer_size": len(self.replay_buffer),
                    "q_table_size": list(self.q_table.shape),
                    "q_table_nonzero_pct": float(len(nonzero_q) / len(q_values_flat) * 100) if len(q_values_flat) > 0 else 0,
                    "q_table_mean": float(np.mean(nonzero_q)) if len(nonzero_q) > 0 else 0,
                    "q_table_max": float(np.max(nonzero_q)) if len(nonzero_q) > 0 else 0,
                    "action_distribution": action_counts,
                    "learning_rate": float(self.learning_rate),
                    "discount_factor": float(self.discount_factor)
                }
        except Exception as e:
            logger.error(f"Error getting training stats: {e}")
            return {}
    
    async def learn_from_backtest_results(self, backtest_results: Dict):
        """Learn from completed backtest results to improve future performance"""
        try:
            strategy_results = backtest_results.get('strategy_results', {})
            
            for strategy, data in strategy_results.items():
                pnl = data.get('pnl', 0)
                win_rate = data.get('win_rate', 0.5)
                trades = data.get('trades', 0)
                
                if trades == 0:
                    continue
                
                # Calculate reward signal for each strategy
                reward = pnl / 100
                
                if win_rate > 0.6:
                    reward *= 1.2
                elif win_rate < 0.4:
                    reward *= 0.8
                
                # Create synthetic experience for this strategy
                state = np.array([
                    0.5,
                    0.05 if 'volatility' in strategy else 0.02,
                    0.5,
                    win_rate,
                    0.5,
                    0.5,
                    0.7,
                    0.3
                ], dtype=np.float32)
                
                # Map strategy to action
                action_map = {
                    'delta_neutral': 0,
                    'volatility_exploitation': 2,
                    'alpha_directional': 3,
                    'arbitrage': 1
                }
                action_idx = action_map.get(strategy, 0)
                
                if self.use_dqn and self.dqn_agent:
                    # Store experience in DQN
                    next_state = state.copy()
                    self.dqn_agent.store_experience(state, action_idx, reward, next_state, done=True)
                    
                    # Train
                    self.dqn_agent.train_step()
                else:
                    # Legacy Q-table update
                    state_idx = self._discretize_state(state)
                    current_q = self.q_table[state_idx, action_idx]
                    new_q = current_q + self.learning_rate * (reward - current_q)
                    self.q_table[state_idx, action_idx] = new_q
                
                self.training_iterations += 1
                self.episode_rewards.append(reward)
                
                logger.info(f"RL learned from {strategy}: reward={reward:.4f}")
            
            # Save model after learning
            await self.save_model()
            
        except Exception as e:
            logger.error(f"Error learning from backtest results: {e}")
    
    async def get_strategy_confidence(self, strategy: str, market_data: Dict) -> float:
        """Get RL model's confidence for a specific strategy in current market conditions"""
        try:
            state = self._build_state(market_data, {})
            
            action_map = {
                'delta_neutral': 0,
                'volatility_exploitation': 2,
                'alpha_directional': 3,
                'arbitrage': 1
            }
            action_idx = action_map.get(strategy, 0)
            
            if self.use_dqn and self.dqn_agent:
                # Get Q-values from DQN
                q_values = self.dqn_agent.get_q_values(state)
                q_value = q_values[action_idx]
                
                # Normalize to confidence [0, 1]
                if np.max(q_values) - np.min(q_values) > 0:
                    confidence = (q_value - np.min(q_values)) / (np.max(q_values) - np.min(q_values))
                else:
                    confidence = 0.5
            else:
                # Legacy Q-table
                state_idx = self._discretize_state(state)
                q_value = self.q_table[state_idx, action_idx]
                
                all_q = self.q_table[state_idx]
                if np.max(all_q) - np.min(all_q) > 0:
                    confidence = (q_value - np.min(all_q)) / (np.max(all_q) - np.min(all_q))
                else:
                    confidence = 0.5
            
            return float(confidence)
            
        except Exception as e:
            logger.error(f"Error getting strategy confidence: {e}")
            return 0.5
    
    async def save_model(self):
        """Save both DQN and Q-table models"""
        try:
            if self.use_dqn and self.dqn_agent:
                self.dqn_agent.save("/app/backend/ml/dqn_model.pt")
            
            # Also save Q-table as backup
            np.savez(
                "/app/backend/ml/rl_model.npz",
                q_table=self.q_table,
                epsilon=self.epsilon,
                training_iterations=self.training_iterations
            )
            logger.info("RL models saved")
        except Exception as e:
            logger.error(f"Error saving RL model: {e}")
    
    async def load_model(self):
        """Load both DQN and Q-table models"""
        try:
            if self.use_dqn and self.dqn_agent:
                self.dqn_agent.load("/app/backend/ml/dqn_model.pt")
                self.training_iterations = self.dqn_agent.training_iterations
            
            # Also try to load Q-table
            try:
                data = np.load("/app/backend/ml/rl_model.npz")
                self.q_table = data['q_table']
                self.epsilon = float(data['epsilon'])
                if not self.use_dqn:
                    self.training_iterations = int(data['training_iterations'])
                logger.info("Q-table loaded as backup")
            except FileNotFoundError:
                pass
                
            logger.info("RL models loaded")
        except Exception as e:
            logger.error(f"Error loading RL model: {e}")
    
    def get_action_size(self, action: str) -> float:
        """Convert action to position size multiplier"""
        size_map = {
            'WAIT': 0.0,
            'BUY_SMALL': 0.25,
            'BUY_MEDIUM': 0.5,
            'BUY_LARGE': 1.0,
            'SELL_SMALL': 0.25,
            'SELL_MEDIUM': 0.5,
            'SELL_LARGE': 1.0
        }
        return size_map.get(action, 0.0)
    
    def is_buy_action(self, action: str) -> bool:
        """Check if action is a buy"""
        return action.startswith('BUY')
    
    def is_sell_action(self, action: str) -> bool:
        """Check if action is a sell"""
        return action.startswith('SELL')
    
    def switch_mode(self, use_dqn: bool):
        """Switch between DQN and Q-table modes"""
        if use_dqn and not self.dqn_agent:
            self.dqn_agent = DQNAgent(
                state_size=self.n_states,
                action_size=self.n_actions,
                hidden_size=64
            )
        self.use_dqn = use_dqn
        logger.info(f"RL Engine switched to {'DQN' if use_dqn else 'Q-table'} mode")

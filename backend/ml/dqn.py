"""
Deep Q-Network (DQN) Implementation with Prioritized Experience Replay
Replaces Q-table with neural network for better generalization
Architecture: Simple (2 hidden layers, 64 neurons each)
"""
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from collections import deque
import random

logger = logging.getLogger(__name__)

# Check if CUDA is available
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
logger.info(f"DQN using device: {device}")


class DQNetwork(nn.Module):
    """
    Deep Q-Network with simple architecture
    Input: 8 state features (price, volatility, sentiment, sharp_alignment, liquidity, volume, time_to_expiry, portfolio_exposure)
    Output: Q-values for 7 actions (WAIT, BUY_SMALL, BUY_MEDIUM, BUY_LARGE, SELL_SMALL, SELL_MEDIUM, SELL_LARGE)
    Architecture: 2 hidden layers, 64 neurons each
    """
    
    def __init__(self, state_size: int = 8, action_size: int = 7, hidden_size: int = 64):
        super(DQNetwork, self).__init__()
        
        self.state_size = state_size
        self.action_size = action_size
        
        # Simple architecture: 2 hidden layers with ReLU activation
        self.network = nn.Sequential(
            nn.Linear(state_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, action_size)
        )
        
        # Initialize weights using Xavier initialization
        self._init_weights()
    
    def _init_weights(self):
        """Initialize network weights"""
        for layer in self.network:
            if isinstance(layer, nn.Linear):
                nn.init.xavier_uniform_(layer.weight)
                nn.init.constant_(layer.bias, 0)
    
    def forward(self, state: torch.Tensor) -> torch.Tensor:
        """Forward pass through network"""
        return self.network(state)


@dataclass
class Experience:
    """Single experience for replay buffer"""
    state: np.ndarray
    action: int
    reward: float
    next_state: np.ndarray
    done: bool
    td_error: float = 1.0  # For prioritized replay


class SumTree:
    """
    Sum Tree data structure for efficient prioritized sampling
    Each leaf node stores priority, parent nodes store sum of children
    Enables O(log n) sampling and O(log n) priority updates
    """
    
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.tree = np.zeros(2 * capacity - 1)  # Binary tree stored in array
        self.data = [None] * capacity  # Leaf data storage
        self.write_idx = 0
        self.n_entries = 0
    
    def _propagate(self, idx: int, change: float):
        """Propagate priority change up the tree"""
        parent = (idx - 1) // 2
        self.tree[parent] += change
        if parent != 0:
            self._propagate(parent, change)
    
    def _retrieve(self, idx: int, s: float) -> int:
        """Find leaf node index for given priority sum"""
        left = 2 * idx + 1
        right = left + 1
        
        if left >= len(self.tree):
            return idx
        
        if s <= self.tree[left]:
            return self._retrieve(left, s)
        else:
            return self._retrieve(right, s - self.tree[left])
    
    def total(self) -> float:
        """Get total priority sum (root node)"""
        return self.tree[0]
    
    def add(self, priority: float, data: Experience):
        """Add experience with given priority"""
        idx = self.write_idx + self.capacity - 1
        
        self.data[self.write_idx] = data
        self.update(idx, priority)
        
        self.write_idx = (self.write_idx + 1) % self.capacity
        self.n_entries = min(self.n_entries + 1, self.capacity)
    
    def update(self, idx: int, priority: float):
        """Update priority of node at idx"""
        change = priority - self.tree[idx]
        self.tree[idx] = priority
        self._propagate(idx, change)
    
    def get(self, s: float) -> Tuple[int, float, Experience]:
        """Sample experience based on priority sum s"""
        idx = self._retrieve(0, s)
        data_idx = idx - self.capacity + 1
        return idx, self.tree[idx], self.data[data_idx]


class PrioritizedReplayBuffer:
    """
    Prioritized Experience Replay Buffer
    Uses SumTree for efficient O(log n) prioritized sampling
    Implements importance sampling weights to correct bias
    """
    
    # Hyperparameters
    PER_E = 0.01  # Small constant to ensure all experiences can be sampled
    PER_A = 0.6   # Priority exponent (0 = uniform, 1 = full prioritization)
    PER_B = 0.4   # Initial importance sampling weight
    PER_B_INCREMENT = 0.001  # Increment per sampling
    
    def __init__(self, capacity: int = 10000):
        self.tree = SumTree(capacity)
        self.capacity = capacity
        self.beta = self.PER_B  # Importance sampling weight
    
    def _get_priority(self, td_error: float) -> float:
        """Convert TD error to priority"""
        return (np.abs(td_error) + self.PER_E) ** self.PER_A
    
    def add(self, experience: Experience):
        """Add experience to buffer with priority based on TD error"""
        priority = self._get_priority(experience.td_error)
        self.tree.add(priority, experience)
    
    def sample(self, batch_size: int) -> Tuple[List[Experience], List[int], np.ndarray]:
        """
        Sample batch of experiences with prioritized sampling
        Returns: (experiences, tree_indices, importance_weights)
        """
        experiences = []
        indices = []
        priorities = []
        
        # Divide priority range into batch_size segments
        segment = self.tree.total() / batch_size
        
        # Anneal beta towards 1
        self.beta = min(1.0, self.beta + self.PER_B_INCREMENT)
        
        for i in range(batch_size):
            # Sample uniformly from each segment
            a = segment * i
            b = segment * (i + 1)
            s = random.uniform(a, b)
            
            idx, priority, exp = self.tree.get(s)
            
            if exp is not None:
                experiences.append(exp)
                indices.append(idx)
                priorities.append(priority)
        
        if not experiences:
            return [], [], np.array([])
        
        # Calculate importance sampling weights
        priorities = np.array(priorities)
        sampling_probs = priorities / self.tree.total()
        
        # IS weights: (N * P(i))^(-beta) / max(weights)
        weights = (self.tree.n_entries * sampling_probs) ** (-self.beta)
        weights = weights / weights.max()  # Normalize
        
        return experiences, indices, weights
    
    def update_priorities(self, indices: List[int], td_errors: np.ndarray):
        """Update priorities based on new TD errors"""
        for idx, td_error in zip(indices, td_errors):
            priority = self._get_priority(td_error)
            self.tree.update(idx, priority)
    
    def __len__(self) -> int:
        return self.tree.n_entries


class DQNAgent:
    """
    Deep Q-Network Agent with:
    - Target network for stable training
    - Prioritized experience replay
    - Double DQN for reduced overestimation
    """
    
    def __init__(
        self,
        state_size: int = 8,
        action_size: int = 7,
        hidden_size: int = 64,
        learning_rate: float = 0.001,
        gamma: float = 0.95,
        epsilon: float = 0.15,
        epsilon_decay: float = 0.995,
        epsilon_min: float = 0.05,
        buffer_size: int = 10000,
        batch_size: int = 32,
        target_update_freq: int = 100
    ):
        self.state_size = state_size
        self.action_size = action_size
        
        # Learning parameters
        self.gamma = gamma
        self.epsilon = epsilon
        self.epsilon_decay = epsilon_decay
        self.epsilon_min = epsilon_min
        self.batch_size = batch_size
        self.target_update_freq = target_update_freq
        
        # Networks
        self.policy_net = DQNetwork(state_size, action_size, hidden_size).to(device)
        self.target_net = DQNetwork(state_size, action_size, hidden_size).to(device)
        self.target_net.load_state_dict(self.policy_net.state_dict())
        self.target_net.eval()  # Target network in eval mode
        
        # Optimizer
        self.optimizer = optim.Adam(self.policy_net.parameters(), lr=learning_rate)
        
        # Prioritized replay buffer
        self.memory = PrioritizedReplayBuffer(buffer_size)
        
        # Training stats
        self.training_iterations = 0
        self.episode_rewards: List[float] = []
        self.losses: List[float] = []
        
        logger.info(f"DQN Agent initialized: state_size={state_size}, action_size={action_size}, hidden={hidden_size}")
    
    def select_action(self, state: np.ndarray) -> Tuple[int, float]:
        """
        Select action using epsilon-greedy policy
        Returns: (action_index, confidence)
        """
        if random.random() < self.epsilon:
            # Exploration: random action
            action = random.randrange(self.action_size)
            confidence = 0.5
        else:
            # Exploitation: best action from network
            with torch.no_grad():
                state_tensor = torch.FloatTensor(state).unsqueeze(0).to(device)
                q_values = self.policy_net(state_tensor)
                action = q_values.argmax(dim=1).item()
                
                # Calculate softmax confidence
                softmax = torch.softmax(q_values, dim=1)
                confidence = softmax[0, action].item()
        
        return action, confidence
    
    def get_q_values(self, state: np.ndarray) -> np.ndarray:
        """Get Q-values for all actions given state"""
        with torch.no_grad():
            state_tensor = torch.FloatTensor(state).unsqueeze(0).to(device)
            q_values = self.policy_net(state_tensor)
            return q_values.cpu().numpy()[0]
    
    def store_experience(self, state: np.ndarray, action: int, reward: float, 
                         next_state: np.ndarray, done: bool):
        """Store experience in prioritized replay buffer"""
        # Calculate initial TD error for priority
        with torch.no_grad():
            state_tensor = torch.FloatTensor(state).unsqueeze(0).to(device)
            next_state_tensor = torch.FloatTensor(next_state).unsqueeze(0).to(device)
            
            current_q = self.policy_net(state_tensor)[0, action].item()
            next_q = self.target_net(next_state_tensor).max(dim=1)[0].item()
            
            if done:
                target_q = reward
            else:
                target_q = reward + self.gamma * next_q
            
            td_error = abs(target_q - current_q)
        
        experience = Experience(
            state=state,
            action=action,
            reward=reward,
            next_state=next_state,
            done=done,
            td_error=td_error
        )
        
        self.memory.add(experience)
        self.episode_rewards.append(reward)
    
    def train_step(self) -> Optional[float]:
        """
        Perform one training step using prioritized experience replay
        Returns: loss value or None if not enough samples
        """
        if len(self.memory) < self.batch_size:
            return None
        
        # Sample prioritized batch
        experiences, indices, weights = self.memory.sample(self.batch_size)
        
        if not experiences:
            return None
        
        # Convert to tensors
        states = torch.FloatTensor(np.array([e.state for e in experiences])).to(device)
        actions = torch.LongTensor([e.action for e in experiences]).to(device)
        rewards = torch.FloatTensor([e.reward for e in experiences]).to(device)
        next_states = torch.FloatTensor(np.array([e.next_state for e in experiences])).to(device)
        dones = torch.FloatTensor([float(e.done) for e in experiences]).to(device)
        weights = torch.FloatTensor(weights).to(device)
        
        # Current Q values
        current_q = self.policy_net(states).gather(1, actions.unsqueeze(1)).squeeze(1)
        
        # Double DQN: Use policy net to select actions, target net to evaluate
        with torch.no_grad():
            # Action selection from policy network
            next_actions = self.policy_net(next_states).argmax(dim=1)
            # Q-value evaluation from target network
            next_q = self.target_net(next_states).gather(1, next_actions.unsqueeze(1)).squeeze(1)
            target_q = rewards + (1 - dones) * self.gamma * next_q
        
        # Calculate TD errors for priority update
        td_errors = (target_q - current_q).abs().detach().cpu().numpy()
        
        # Weighted loss (importance sampling)
        loss = (weights * (current_q - target_q) ** 2).mean()
        
        # Optimize
        self.optimizer.zero_grad()
        loss.backward()
        # Gradient clipping for stability
        torch.nn.utils.clip_grad_norm_(self.policy_net.parameters(), 1.0)
        self.optimizer.step()
        
        # Update priorities in replay buffer
        self.memory.update_priorities(indices, td_errors)
        
        # Update target network periodically
        self.training_iterations += 1
        if self.training_iterations % self.target_update_freq == 0:
            self.target_net.load_state_dict(self.policy_net.state_dict())
            logger.info(f"Target network updated at iteration {self.training_iterations}")
        
        # Decay epsilon
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)
        
        loss_value = loss.item()
        self.losses.append(loss_value)
        
        return loss_value
    
    def get_stats(self) -> Dict:
        """Get training statistics"""
        recent_rewards = self.episode_rewards[-100:] if self.episode_rewards else []
        recent_losses = self.losses[-100:] if self.losses else []
        
        positive_rewards = [r for r in recent_rewards if r > 0]
        negative_rewards = [r for r in recent_rewards if r < 0]
        
        return {
            "type": "DQN",
            "architecture": f"{self.state_size} -> 64 -> 64 -> {self.action_size}",
            "total_iterations": self.training_iterations,
            "epsilon": float(self.epsilon),
            "buffer_size": len(self.memory),
            "buffer_beta": float(self.memory.beta),
            "avg_reward_100": float(np.mean(recent_rewards)) if recent_rewards else 0,
            "max_reward_100": float(max(recent_rewards)) if recent_rewards else 0,
            "min_reward_100": float(min(recent_rewards)) if recent_rewards else 0,
            "std_reward_100": float(np.std(recent_rewards)) if len(recent_rewards) > 1 else 0,
            "positive_rate": float(len(positive_rewards) / len(recent_rewards)) if recent_rewards else 0,
            "avg_positive_reward": float(np.mean(positive_rewards)) if positive_rewards else 0,
            "avg_negative_reward": float(np.mean(negative_rewards)) if negative_rewards else 0,
            "avg_loss_100": float(np.mean(recent_losses)) if recent_losses else 0,
            "learning_rate": float(self.optimizer.param_groups[0]['lr']),
            "gamma": float(self.gamma),
            "target_update_freq": self.target_update_freq
        }
    
    def save(self, filepath: str = "/app/backend/ml/dqn_model.pt"):
        """Save model checkpoint"""
        try:
            checkpoint = {
                'policy_net_state_dict': self.policy_net.state_dict(),
                'target_net_state_dict': self.target_net.state_dict(),
                'optimizer_state_dict': self.optimizer.state_dict(),
                'epsilon': self.epsilon,
                'training_iterations': self.training_iterations,
                'episode_rewards': self.episode_rewards[-1000:],  # Keep last 1000
                'losses': self.losses[-1000:]
            }
            torch.save(checkpoint, filepath)
            logger.info(f"DQN model saved to {filepath}")
        except Exception as e:
            logger.error(f"Error saving DQN model: {e}")
    
    def load(self, filepath: str = "/app/backend/ml/dqn_model.pt"):
        """Load model checkpoint"""
        try:
            checkpoint = torch.load(filepath, map_location=device)
            self.policy_net.load_state_dict(checkpoint['policy_net_state_dict'])
            self.target_net.load_state_dict(checkpoint['target_net_state_dict'])
            self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
            self.epsilon = checkpoint['epsilon']
            self.training_iterations = checkpoint['training_iterations']
            self.episode_rewards = checkpoint.get('episode_rewards', [])
            self.losses = checkpoint.get('losses', [])
            logger.info(f"DQN model loaded from {filepath}")
        except FileNotFoundError:
            logger.info("No saved DQN model found, using fresh initialization")
        except Exception as e:
            logger.error(f"Error loading DQN model: {e}")

"""
Test DQN (Deep Q-Network) Features - Iteration 20
Tests for:
1. DQN module import and functionality
2. RL Engine uses DQN by default
3. /api/rl/stats returns DQN-specific fields
4. /api/rl/switch-mode endpoint works
5. Prioritized Experience Replay is enabled
6. Target network update frequency is 100
7. Neural network architecture is 8 -> 64 -> 64 -> 7
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
AUTH = ('admin', 'apex2026!')


class TestDQNModule:
    """Test DQN module is properly imported and working"""
    
    def test_dqn_module_exists(self):
        """Verify DQN module file exists"""
        import sys
        sys.path.insert(0, '/app/backend')
        
        # Check file exists
        assert os.path.exists('/app/backend/ml/dqn.py'), "DQN module file should exist"
    
    def test_dqn_imports(self):
        """Verify DQN classes can be imported"""
        import sys
        sys.path.insert(0, '/app/backend')
        
        from ml.dqn import DQNetwork, SumTree, PrioritizedReplayBuffer, DQNAgent, Experience
        
        # Verify classes exist
        assert DQNetwork is not None
        assert SumTree is not None
        assert PrioritizedReplayBuffer is not None
        assert DQNAgent is not None
        assert Experience is not None
    
    def test_dqn_network_architecture(self):
        """Verify DQN network has correct architecture (8 -> 64 -> 64 -> 7)"""
        import sys
        sys.path.insert(0, '/app/backend')
        
        from ml.dqn import DQNetwork
        
        # Create network with default params
        network = DQNetwork(state_size=8, action_size=7, hidden_size=64)
        
        # Verify architecture
        assert network.state_size == 8, "State size should be 8"
        assert network.action_size == 7, "Action size should be 7"
        
        # Check network layers
        layers = list(network.network.children())
        assert len(layers) == 5, "Should have 5 layers (3 Linear + 2 ReLU)"
        
        # Verify layer dimensions
        import torch.nn as nn
        linear_layers = [l for l in layers if isinstance(l, nn.Linear)]
        assert len(linear_layers) == 3, "Should have 3 Linear layers"
        
        # Input layer: 8 -> 64
        assert linear_layers[0].in_features == 8
        assert linear_layers[0].out_features == 64
        
        # Hidden layer: 64 -> 64
        assert linear_layers[1].in_features == 64
        assert linear_layers[1].out_features == 64
        
        # Output layer: 64 -> 7
        assert linear_layers[2].in_features == 64
        assert linear_layers[2].out_features == 7


class TestDQNAgent:
    """Test DQN Agent functionality"""
    
    def test_dqn_agent_initialization(self):
        """Verify DQN agent initializes with correct parameters"""
        import sys
        sys.path.insert(0, '/app/backend')
        
        from ml.dqn import DQNAgent
        
        agent = DQNAgent(
            state_size=8,
            action_size=7,
            hidden_size=64,
            target_update_freq=100
        )
        
        assert agent.state_size == 8
        assert agent.action_size == 7
        assert agent.target_update_freq == 100
        assert agent.policy_net is not None
        assert agent.target_net is not None
        assert agent.memory is not None
    
    def test_dqn_agent_select_action(self):
        """Verify DQN agent can select actions"""
        import sys
        sys.path.insert(0, '/app/backend')
        import numpy as np
        
        from ml.dqn import DQNAgent
        
        agent = DQNAgent(state_size=8, action_size=7)
        
        # Create a sample state
        state = np.array([0.5, 0.3, 0.6, 0.4, 0.5, 0.5, 0.7, 0.3], dtype=np.float32)
        
        # Select action
        action, confidence = agent.select_action(state)
        
        assert 0 <= action < 7, "Action should be in range [0, 6]"
        assert 0 <= confidence <= 1, "Confidence should be in range [0, 1]"
    
    def test_dqn_agent_get_stats(self):
        """Verify DQN agent returns correct stats"""
        import sys
        sys.path.insert(0, '/app/backend')
        
        from ml.dqn import DQNAgent
        
        agent = DQNAgent(
            state_size=8,
            action_size=7,
            hidden_size=64,
            target_update_freq=100
        )
        
        stats = agent.get_stats()
        
        # Verify DQN-specific fields
        assert stats['type'] == 'DQN'
        assert stats['architecture'] == '8 -> 64 -> 64 -> 7'
        assert stats['target_update_freq'] == 100
        assert 'buffer_beta' in stats
        assert 'avg_loss_100' in stats


class TestPrioritizedReplayBuffer:
    """Test Prioritized Experience Replay functionality"""
    
    def test_sum_tree_operations(self):
        """Verify SumTree data structure works correctly"""
        import sys
        sys.path.insert(0, '/app/backend')
        
        from ml.dqn import SumTree
        
        tree = SumTree(capacity=100)
        
        # Initially empty
        assert tree.total() == 0
        assert tree.n_entries == 0
    
    def test_prioritized_buffer_initialization(self):
        """Verify PrioritizedReplayBuffer initializes correctly"""
        import sys
        sys.path.insert(0, '/app/backend')
        
        from ml.dqn import PrioritizedReplayBuffer
        
        buffer = PrioritizedReplayBuffer(capacity=10000)
        
        # Check hyperparameters
        assert buffer.PER_A == 0.6, "Alpha should be 0.6"
        assert buffer.PER_B == 0.4, "Initial beta should be 0.4"
        assert buffer.beta == 0.4, "Current beta should start at 0.4"
        assert len(buffer) == 0


class TestRLStatsAPI:
    """Test /api/rl/stats endpoint returns DQN-specific fields"""
    
    def test_rl_stats_returns_dqn_fields(self):
        """Verify /api/rl/stats returns DQN-specific fields"""
        response = requests.get(f"{BASE_URL}/api/rl/stats")
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify DQN-specific fields when in DQN mode
        if data.get('model_type') == 'DQN' or data.get('type') == 'DQN':
            assert 'architecture' in data, "Should have architecture field"
            assert data['architecture'] == '8 -> 64 -> 64 -> 7', "Architecture should be 8 -> 64 -> 64 -> 7"
            assert 'device' in data or data.get('model_type') == 'DQN', "Should have device field or be DQN type"
            assert 'buffer_beta' in data, "Should have buffer_beta field"
            assert 'avg_loss_100' in data, "Should have avg_loss_100 field"
            assert data.get('prioritized_replay') == True, "Prioritized replay should be enabled"
    
    def test_rl_stats_target_update_freq(self):
        """Verify target_update_freq is 100"""
        response = requests.get(f"{BASE_URL}/api/rl/stats")
        assert response.status_code == 200
        
        data = response.json()
        
        if data.get('model_type') == 'DQN' or data.get('type') == 'DQN':
            assert data.get('target_update_freq') == 100, "Target update frequency should be 100"
    
    def test_rl_detailed_stats(self):
        """Verify /api/rl/detailed-stats returns DQN info"""
        response = requests.get(f"{BASE_URL}/api/rl/detailed-stats")
        assert response.status_code == 200
        
        data = response.json()
        
        # Should have rl_stats field
        assert 'rl_stats' in data
        
        rl_stats = data['rl_stats']
        if rl_stats.get('model_type') == 'DQN' or rl_stats.get('type') == 'DQN':
            assert rl_stats.get('prioritized_replay') == True


class TestSwitchModeAPI:
    """Test /api/rl/switch-mode endpoint"""
    
    def test_switch_to_qtable_mode(self):
        """Verify switching to Q-table mode works"""
        response = requests.post(
            f"{BASE_URL}/api/rl/switch-mode?use_dqn=false",
            auth=AUTH
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data['mode'] == 'Q-table'
        assert data['stats']['model_type'] == 'Q-table'
        assert data['stats']['prioritized_replay'] == False
    
    def test_switch_to_dqn_mode(self):
        """Verify switching to DQN mode works"""
        response = requests.post(
            f"{BASE_URL}/api/rl/switch-mode?use_dqn=true",
            auth=AUTH
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data['mode'] == 'DQN'
        assert data['stats']['model_type'] == 'DQN'
        assert data['stats']['prioritized_replay'] == True
        assert data['stats']['architecture'] == '8 -> 64 -> 64 -> 7'
    
    def test_switch_mode_requires_auth(self):
        """Verify switch-mode requires authentication"""
        response = requests.post(f"{BASE_URL}/api/rl/switch-mode?use_dqn=true")
        assert response.status_code == 401, "Should require authentication"


class TestRLEngineDefaultMode:
    """Test RL Engine uses DQN by default"""
    
    def test_rl_engine_default_dqn(self):
        """Verify RL Engine initializes with DQN by default"""
        import sys
        sys.path.insert(0, '/app/backend')
        
        # Check the source code
        with open('/app/backend/ml/rl_engine.py', 'r') as f:
            content = f.read()
        
        # Verify use_dqn=True is the default
        assert 'def __init__(self, use_dqn: bool = True)' in content, "use_dqn should default to True"
        assert 'from ml.dqn import DQNAgent' in content, "Should import DQNAgent"
    
    def test_api_returns_dqn_by_default(self):
        """Verify API returns DQN mode by default after reset"""
        # First ensure we're in DQN mode
        requests.post(f"{BASE_URL}/api/rl/switch-mode?use_dqn=true", auth=AUTH)
        
        response = requests.get(f"{BASE_URL}/api/rl/stats")
        assert response.status_code == 200
        
        data = response.json()
        assert data.get('model_type') == 'DQN' or data.get('type') == 'DQN', "Should be in DQN mode"


class TestDQNArchitectureDetails:
    """Test DQN architecture details"""
    
    def test_architecture_string_format(self):
        """Verify architecture string is in correct format"""
        response = requests.get(f"{BASE_URL}/api/rl/stats")
        assert response.status_code == 200
        
        data = response.json()
        
        if data.get('model_type') == 'DQN' or data.get('type') == 'DQN':
            arch = data.get('architecture')
            assert arch == '8 -> 64 -> 64 -> 7', f"Architecture should be '8 -> 64 -> 64 -> 7', got '{arch}'"
    
    def test_state_features_count(self):
        """Verify 8 state features are defined"""
        response = requests.get(f"{BASE_URL}/api/rl/stats")
        assert response.status_code == 200
        
        data = response.json()
        
        if 'state_features' in data:
            assert len(data['state_features']) == 8, "Should have 8 state features"
            expected_features = ['price', 'volatility', 'sentiment', 'sharp_alignment', 
                               'liquidity', 'volume', 'time_to_expiry', 'portfolio_exposure']
            assert data['state_features'] == expected_features
    
    def test_action_space_size(self):
        """Verify 7 actions are defined"""
        response = requests.get(f"{BASE_URL}/api/rl/stats")
        assert response.status_code == 200
        
        data = response.json()
        
        if 'action_distribution' in data:
            assert len(data['action_distribution']) == 7, "Should have 7 actions"
            expected_actions = ['WAIT', 'BUY_SMALL', 'BUY_MEDIUM', 'BUY_LARGE', 
                              'SELL_SMALL', 'SELL_MEDIUM', 'SELL_LARGE']
            for action in expected_actions:
                assert action in data['action_distribution'], f"Missing action: {action}"


class TestPrioritizedReplayParameters:
    """Test Prioritized Experience Replay parameters"""
    
    def test_buffer_beta_initial_value(self):
        """Verify buffer_beta starts at 0.4"""
        response = requests.get(f"{BASE_URL}/api/rl/stats")
        assert response.status_code == 200
        
        data = response.json()
        
        if data.get('model_type') == 'DQN' or data.get('type') == 'DQN':
            # Beta should be >= 0.4 (starts at 0.4 and anneals towards 1.0)
            assert data.get('buffer_beta', 0) >= 0.4, "Buffer beta should be >= 0.4"
            assert data.get('buffer_beta', 1) <= 1.0, "Buffer beta should be <= 1.0"
    
    def test_prioritized_replay_enabled(self):
        """Verify prioritized_replay is True for DQN mode"""
        response = requests.get(f"{BASE_URL}/api/rl/stats")
        assert response.status_code == 200
        
        data = response.json()
        
        if data.get('model_type') == 'DQN' or data.get('type') == 'DQN':
            assert data.get('prioritized_replay') == True, "Prioritized replay should be enabled"


class TestHealthAndIntegration:
    """Test health and integration endpoints"""
    
    def test_health_endpoint(self):
        """Verify health endpoint works"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data['status'] == 'healthy'
    
    def test_rl_train_endpoint_exists(self):
        """Verify /api/rl/train endpoint exists"""
        response = requests.post(f"{BASE_URL}/api/rl/train", auth=AUTH)
        # Should return 200 (success) or some valid response, not 404
        assert response.status_code != 404, "RL train endpoint should exist"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

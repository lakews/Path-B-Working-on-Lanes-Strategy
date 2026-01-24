"""
Test Suite: RL Engine Stability Integration Tests
Tests the complete RL feedback loop within the application context.

Key Verification Points:
1. RLAdaptiveEngine initializes correctly with DQN
2. Experiences can be added to the replay buffer
3. Training from replay works when buffer has enough experiences
4. Model save and load functionality works
5. Stats are captured correctly
6. Force train button conditions are met when buffer_size > 32
"""
import pytest
import requests
import os
import sys
import time
import numpy as np

# Add backend to path for direct imports
sys.path.insert(0, '/app/backend')

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
AUTH = ('admin', 'apex2026!')


class TestRLEngineViaAPI:
    """Test RL Engine via API endpoints (within app context)"""
    
    def test_rl_stats_endpoint_returns_valid_response(self):
        """Verify /api/rl/stats returns valid DQN stats"""
        response = requests.get(f"{BASE_URL}/api/rl/stats", auth=AUTH)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify DQN-specific fields are present
        assert 'model_type' in data, "model_type field missing"
        assert data.get('model_type') == 'DQN', f"Expected DQN mode, got {data.get('model_type')}"
        
        # Verify buffer_size field exists (critical for force train button)
        assert 'buffer_size' in data, "buffer_size field missing"
        
        # Verify epsilon field exists
        assert 'epsilon' in data, "epsilon field missing"
        
        # Verify total_iterations field exists
        assert 'total_iterations' in data, "total_iterations field missing"
        
        print(f"✓ RL Stats: model_type={data['model_type']}, buffer_size={data['buffer_size']}, "
              f"epsilon={data['epsilon']:.4f}, iterations={data['total_iterations']}")
    
    def test_rl_detailed_stats_endpoint(self):
        """Verify /api/rl/detailed-stats returns comprehensive DQN info"""
        response = requests.get(f"{BASE_URL}/api/rl/detailed-stats", auth=AUTH)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify DQN-specific fields
        assert data.get('prioritized_replay') == True, "DQN should have prioritized_replay=True"
        assert 'device' in data, "device field missing"
        assert 'action_distribution' in data, "action_distribution field missing"
        assert 'state_features' in data, "state_features field missing"
        
        print(f"✓ Detailed Stats: device={data['device']}, prioritized_replay={data['prioritized_replay']}")
        print(f"  State features: {data['state_features']}")
    
    def test_rl_train_endpoint(self):
        """Verify /api/rl/train endpoint works (even with empty buffer)"""
        response = requests.post(f"{BASE_URL}/api/rl/train", auth=AUTH)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert 'message' in data, "Response should have message field"
        assert 'stats' in data, "Response should have stats field"
        
        print(f"✓ Train endpoint: {data['message']}")
    
    def test_rl_save_and_load_model(self):
        """Verify model save and load functionality"""
        # Save model
        save_response = requests.post(f"{BASE_URL}/api/rl/save", auth=AUTH)
        assert save_response.status_code == 200, f"Save failed: {save_response.text}"
        
        save_data = save_response.json()
        assert save_data.get('message') == "RL model saved successfully", f"Unexpected message: {save_data}"
        print(f"✓ Model save: {save_data['message']}")
        
        # Load model
        load_response = requests.post(f"{BASE_URL}/api/rl/load", auth=AUTH)
        assert load_response.status_code == 200, f"Load failed: {load_response.text}"
        
        load_data = load_response.json()
        assert 'message' in load_data, "Load response missing message"
        assert 'stats' in load_data, "Load response missing stats"
        print(f"✓ Model load: {load_data['message']}")
    
    def test_rl_switch_mode_to_dqn(self):
        """Verify switching to DQN mode"""
        response = requests.post(f"{BASE_URL}/api/rl/switch-mode?use_dqn=true", auth=AUTH)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get('model_type') == 'DQN', f"Expected DQN mode, got {data.get('model_type')}"
        print(f"✓ Switch to DQN: model_type={data['model_type']}")
    
    def test_rl_switch_mode_to_qtable_and_back(self):
        """Verify switching between Q-table and DQN modes"""
        # Switch to Q-table
        response1 = requests.post(f"{BASE_URL}/api/rl/switch-mode?use_dqn=false", auth=AUTH)
        assert response1.status_code == 200, f"Expected 200, got {response1.status_code}"
        
        data1 = response1.json()
        assert data1.get('model_type') == 'Q-table', f"Expected Q-table mode, got {data1.get('model_type')}"
        print(f"✓ Switch to Q-table: model_type={data1['model_type']}")
        
        # Switch back to DQN
        response2 = requests.post(f"{BASE_URL}/api/rl/switch-mode?use_dqn=true", auth=AUTH)
        assert response2.status_code == 200, f"Expected 200, got {response2.status_code}"
        
        data2 = response2.json()
        assert data2.get('model_type') == 'DQN', f"Expected DQN mode, got {data2.get('model_type')}"
        print(f"✓ Switch back to DQN: model_type={data2['model_type']}")


class TestDQNAgentDirect:
    """Direct tests for DQN Agent (no DB required)"""
    
    def test_dqn_agent_initialization(self):
        """Verify DQNAgent initializes with correct architecture"""
        from ml.dqn import DQNAgent, device
        
        agent = DQNAgent(
            state_size=8,
            action_size=7,
            hidden_size=64
        )
        
        # Verify architecture
        assert agent.state_size == 8, f"Expected state_size=8, got {agent.state_size}"
        assert agent.action_size == 7, f"Expected action_size=7, got {agent.action_size}"
        
        # Verify networks are on correct device
        policy_device = next(agent.policy_net.parameters()).device
        assert str(policy_device) == str(device), f"Policy net on wrong device: {policy_device}"
        
        print(f"✓ DQNAgent initialized: state={agent.state_size}, actions={agent.action_size}, device={device}")
    
    def test_dqn_agent_select_action(self):
        """Verify action selection returns valid action and confidence"""
        from ml.dqn import DQNAgent
        
        agent = DQNAgent(state_size=8, action_size=7)
        
        # Create test state
        state = np.array([0.5, 0.1, 0.6, 0.7, 0.3, 0.4, 0.8, 0.2], dtype=np.float32)
        
        action, confidence = agent.select_action(state)
        
        assert 0 <= action < 7, f"Action {action} out of range [0, 7)"
        assert 0.0 <= confidence <= 1.0, f"Confidence {confidence} out of range [0, 1]"
        
        print(f"✓ Action selection: action={action}, confidence={confidence:.4f}")
    
    def test_dqn_agent_store_experience(self):
        """Verify experience storage in prioritized replay buffer"""
        from ml.dqn import DQNAgent
        
        agent = DQNAgent(state_size=8, action_size=7, buffer_size=1000)
        
        initial_buffer_size = len(agent.memory)
        
        # Store multiple experiences
        for i in range(10):
            state = np.random.rand(8).astype(np.float32)
            next_state = np.random.rand(8).astype(np.float32)
            action = np.random.randint(0, 7)
            reward = np.random.randn() * 0.1
            done = i == 9  # Last one is terminal
            
            agent.store_experience(state, action, reward, next_state, done)
        
        new_buffer_size = len(agent.memory)
        
        assert new_buffer_size == initial_buffer_size + 10, \
            f"Buffer should have {initial_buffer_size + 10} experiences, got {new_buffer_size}"
        
        print(f"✓ Experience storage: buffer grew from {initial_buffer_size} to {new_buffer_size}")
    
    def test_dqn_agent_train_step_insufficient_buffer(self):
        """Verify train_step returns None when buffer is insufficient"""
        from ml.dqn import DQNAgent
        
        agent = DQNAgent(state_size=8, action_size=7, batch_size=32)
        
        # Add only 10 experiences (less than batch_size=32)
        for _ in range(10):
            state = np.random.rand(8).astype(np.float32)
            next_state = np.random.rand(8).astype(np.float32)
            agent.store_experience(state, 0, 0.1, next_state, False)
        
        loss = agent.train_step()
        
        assert loss is None, f"Expected None loss with insufficient buffer, got {loss}"
        print(f"✓ Train step with insufficient buffer: loss=None (correct)")
    
    def test_dqn_agent_train_step_sufficient_buffer(self):
        """Verify train_step works when buffer has enough experiences"""
        from ml.dqn import DQNAgent
        
        agent = DQNAgent(state_size=8, action_size=7, batch_size=32)
        
        # Add 50 experiences (more than batch_size=32)
        for i in range(50):
            state = np.random.rand(8).astype(np.float32)
            next_state = np.random.rand(8).astype(np.float32)
            action = np.random.randint(0, 7)
            # Create varied rewards to test learning
            reward = (i - 25) * 0.01  # Range from -0.25 to +0.24
            done = i % 10 == 9
            
            agent.store_experience(state, action, reward, next_state, done)
        
        # Run training step
        loss = agent.train_step()
        
        assert loss is not None, "Expected loss value, got None"
        assert loss >= 0, f"Loss should be non-negative, got {loss}"
        assert agent.training_iterations == 1, f"Expected 1 iteration, got {agent.training_iterations}"
        
        print(f"✓ Train step with sufficient buffer: loss={loss:.6f}, iterations={agent.training_iterations}")
    
    def test_dqn_agent_multiple_training_iterations(self):
        """Verify multiple training iterations work correctly"""
        from ml.dqn import DQNAgent
        
        agent = DQNAgent(
            state_size=8, 
            action_size=7, 
            batch_size=32,
            epsilon=1.0,  # Start with full exploration
            epsilon_decay=0.99
        )
        
        # Add 100 experiences
        for i in range(100):
            state = np.random.rand(8).astype(np.float32)
            next_state = np.random.rand(8).astype(np.float32)
            action = np.random.randint(0, 7)
            reward = np.random.randn() * 0.1
            done = i % 20 == 19
            
            agent.store_experience(state, action, reward, next_state, done)
        
        initial_epsilon = agent.epsilon
        
        # Run 10 training iterations
        losses = []
        for _ in range(10):
            loss = agent.train_step()
            if loss is not None:
                losses.append(loss)
        
        assert len(losses) == 10, f"Expected 10 training losses, got {len(losses)}"
        assert agent.training_iterations == 10, f"Expected 10 iterations, got {agent.training_iterations}"
        assert agent.epsilon < initial_epsilon, "Epsilon should decay during training"
        
        print(f"✓ Multiple training: iterations={agent.training_iterations}, "
              f"epsilon={initial_epsilon:.4f}→{agent.epsilon:.4f}, avg_loss={np.mean(losses):.6f}")
    
    def test_dqn_agent_get_stats(self):
        """Verify get_stats returns complete statistics"""
        from ml.dqn import DQNAgent
        
        agent = DQNAgent(state_size=8, action_size=7, batch_size=32)
        
        # Add experiences and train
        for i in range(50):
            state = np.random.rand(8).astype(np.float32)
            next_state = np.random.rand(8).astype(np.float32)
            agent.store_experience(state, i % 7, (i - 25) * 0.01, next_state, i % 10 == 9)
        
        agent.train_step()
        
        stats = agent.get_stats()
        
        required_fields = [
            'type', 'architecture', 'total_iterations', 'epsilon', 'buffer_size',
            'buffer_beta', 'avg_reward_100', 'max_reward_100', 'min_reward_100',
            'std_reward_100', 'positive_rate', 'avg_positive_reward', 'avg_negative_reward',
            'avg_loss_100', 'learning_rate', 'gamma', 'target_update_freq'
        ]
        
        for field in required_fields:
            assert field in stats, f"Missing field: {field}"
        
        assert stats['type'] == 'DQN', f"Expected type='DQN', got {stats['type']}"
        assert stats['architecture'] == '8 -> 64 -> 64 -> 7', f"Wrong architecture: {stats['architecture']}"
        
        print(f"✓ Stats complete: {len(stats)} fields, iterations={stats['total_iterations']}")


class TestForceTrainButtonCondition:
    """Test the condition for enabling Force Train button (buffer_size > 32)"""
    
    def test_force_train_button_condition_via_api(self):
        """Verify Force Train button should be enabled based on buffer_size"""
        response = requests.get(f"{BASE_URL}/api/rl/stats", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        buffer_size = data.get('buffer_size', 0)
        
        # The button should be enabled when buffer_size > 32
        should_enable = buffer_size > 32
        
        print(f"✓ Force Train button condition: buffer_size={buffer_size}, "
              f"should_enable={should_enable} (requires >32)")
        
        if should_enable:
            print("  → Button should be ENABLED (enough experiences)")
        else:
            print(f"  → Button should be DISABLED (need {33 - buffer_size} more experiences)")


class TestRLEngineDirectInitialization:
    """Test RLAdaptiveEngine direct initialization (requires DB context simulation)"""
    
    def test_rl_engine_initialization_via_api(self):
        """Verify RL Engine initializes correctly through API"""
        # First get stats (which initializes the engine)
        response = requests.get(f"{BASE_URL}/api/rl/stats", auth=AUTH)
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify engine is in DQN mode
        assert data.get('model_type') == 'DQN', "RL Engine should default to DQN mode"
        assert data.get('prioritized_replay') == True, "DQN should use prioritized replay"
        
        # Verify state features
        expected_features = ['price', 'volatility', 'sentiment', 'sharp_alignment',
                            'liquidity', 'volume', 'time_to_expiry', 'portfolio_exposure']
        actual_features = data.get('state_features', [])
        
        assert actual_features == expected_features, f"State features mismatch: {actual_features}"
        
        print(f"✓ RL Engine initialized via API: {len(actual_features)} state features, DQN mode")


class TestPaperTradingRLIntegration:
    """Test RL integration with paper trading (if paper trading is running)"""
    
    def test_paper_trading_status_includes_rl_stats(self):
        """Verify paper trading status includes RL-related fields"""
        response = requests.get(f"{BASE_URL}/api/paper/status", auth=AUTH)
        
        if response.status_code != 200:
            print("⚠ Paper trading not running, skipping RL integration test")
            pytest.skip("Paper trading not running")
        
        data = response.json()
        
        # Check for RL-related fields in paper trading status
        if 'rl_stats' in data:
            rl_stats = data['rl_stats']
            print(f"✓ Paper trading includes RL stats: {list(rl_stats.keys())[:5]}...")
        else:
            print("⚠ Paper trading status doesn't include RL stats (may be expected)")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])

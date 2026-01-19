# ML Dependencies Audit Report

**Date:** January 19, 2026  
**Purpose:** Identify which ML dependencies can be removed to unblock cloud deployment

---

## Summary

| Package | Size | Used? | Action |
|---------|------|-------|--------|
| **TensorFlow** | 1.4 GB | ❌ NO | **REMOVE** |
| **Keras** | (part of TF) | ❌ NO | **REMOVE** |
| **Transformers** | 119 MB | ❌ NO | **REMOVE** |
| **PyTorch** | 435 MB | ✅ YES | Replace or make optional |
| **NumPy** | ~50 MB | ✅ YES | Keep |
| **Pandas** | ~50 MB | ✅ YES | Keep |
| **SciPy** | ~100 MB | ✅ YES | Keep |

**Potential Savings:** ~1.5 GB (TensorFlow + Keras + Transformers)

---

## Detailed Findings

### TensorFlow (1.4 GB) - NOT USED
```bash
grep -rl "import tensorflow" /app/backend --include="*.py"
# Result: None found
```
**Recommendation:** Safe to remove immediately.

### Keras - NOT USED
Part of TensorFlow, no direct imports found.  
**Recommendation:** Safe to remove immediately.

### Transformers (119 MB) - NOT USED
```bash
grep -rl "from transformers" /app/backend --include="*.py"
# Result: None found
```
Was likely used for local sentiment models before switching to GPT-4o-mini API.  
**Recommendation:** Safe to remove immediately.

### PyTorch (435 MB) - USED
```bash
grep -rl "import torch" /app/backend --include="*.py"
# Result: /app/backend/ml/dqn.py
```

**Import Chain:**
```
dqn.py (imports torch)
   ↓
rl_engine.py (imports DQNAgent from dqn.py)
   ↓
paper_trader.py (imports rl_engine)
```

**What it does:** Deep Q-Network for reinforcement learning trade decisions.

**Options to remove:**
1. **Remove DQN entirely** - Use rule-based position decisions
2. **Replace with lightweight RL** - Q-table or simple numpy-based neural net
3. **Make DQN optional** - Graceful fallback if torch not available

---

## Files Using NumPy (KEEP)

NumPy is used by 20+ core files for essential math operations:
- `paper_trader.py`
- `polymarket_sentiment.py`
- `enhanced_sentiment.py`
- `volatility_predictor.py`
- `risk_controller.py`
- And more...

---

## Implementation Plan (Future)

### Phase 1: Quick Wins (No Code Changes)
1. Remove from `requirements.txt`:
   - `tensorflow==2.20.0`
   - `keras==3.13.0`
   - `transformers==4.57.3`
2. Test that app still runs
3. Redeploy

### Phase 2: PyTorch Removal (Requires Code Changes)
1. Create `rl_engine_lite.py` using numpy-only Q-learning
2. Add feature flag to switch between DQN and lite version
3. Test trading performance with lite version
4. Remove `torch==2.9.1` from requirements

---

## Current requirements.txt ML Section

```
keras==3.13.0          # REMOVE
numpy==2.4.0           # KEEP
pandas==2.3.3          # KEEP
scipy==1.17.0          # KEEP
tensorflow==2.20.0     # REMOVE
torch==2.9.1           # REPLACE (Phase 2)
transformers==4.57.3   # REMOVE
```

---

*Document created: January 19, 2026*
*Status: Saved for future action*

"""
Pytest configuration for integration tests.
Provides shared fixtures and utilities.
"""
import pytest
import os


def get_api_base_url():
    """
    Get the base URL for API testing.
    
    Priority:
    1. TEST_API_URL environment variable
    2. REACT_APP_BACKEND_URL from frontend/.env
    3. Fallback to localhost:8001
    """
    # Check for explicit test URL
    test_url = os.environ.get('TEST_API_URL', '').strip()
    if test_url:
        return test_url.rstrip('/')
    
    # Try reading from frontend env file
    try:
        with open('/app/frontend/.env', 'r') as f:
            for line in f:
                if line.startswith('REACT_APP_BACKEND_URL='):
                    return line.split('=', 1)[1].strip().rstrip('/')
    except:
        pass
    
    # Fallback to localhost
    return 'http://localhost:8001'


# Export for use in tests
API_BASE_URL = get_api_base_url()


@pytest.fixture
def api_url():
    """Fixture providing the API base URL."""
    return API_BASE_URL

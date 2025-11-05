'''
Unit tests for health check endpoints.
These are smoke tests - if they fail, nothing else will work.
'''
import pytest

# =============================================================================
# Smoke Tests - Critical endpoints
# =============================================================================

@pytest.mark.smoke
@pytest.mark.unit
def test_health_endpoint_returns_200(client):
    '''
    SMOKE TEST: /health endpoint returns 200 OK.

    This is the most basic test - if this fails, API is down.
    '''
    # Arrange (setup) - nothing needed, client is ready

    # Act (execute) - send GET request to /health
    response = client.get('/health')

    # Assert (verify) - check status code
    assert response.status_code == 200


@pytest.mark.smoke
@pytest.mark.unit
def test_health_endpoint_returns_ok_json(client):
    '''
    SMOKE TEST: /health endpoint returns correct JSON.

    Verifies the response structure and content.
    '''
    # Act
    response = client.get('/health')

    # Assert
    assert response.json == {'ok': True}


@pytest.mark.unit
def test_health_endpoint_content_type(client):
    '''
    Unit test: /health returns correct Content-Type header.
    '''
    # Act
    response = client.get('/health')

    # Assert
    assert response.content_type == 'application/json; charset=utf-8'


# =============================================================================
# Tests for /live endpoint (liveness probe)
# =============================================================================

@pytest.mark.smoke
@pytest.mark.unit
def test_live_endpoint_returns_200(client):
    '''
    SMOKE TEST: /live endpoint returns 200 OK.
    '''
    response = client.get('/live')
    assert response.status_code == 200


@pytest.mark.unit
def test_live_endpoint_returns_correct_structure(client):
    '''
    Unit test: /live returns expected JSON structure.
    '''
    # Act
    response = client.get('/live')
    data = response.json

    # Assert - check all expected fields exist
    assert 'status' in data
    assert 'version' in data
    assert 'uptime_seconds' in data
    assert 'timestamp' in data

    # Assert - check field types
    assert data['status'] == 'alive'
    assert isinstance(data['uptime_seconds'], (int, float))
    assert isinstance(data['timestamp'], str)


# =============================================================================
# Tests for /version endpoint
# =============================================================================

@pytest.mark.unit
def test_version_endpoint_returns_200(client):
    '''
    Unit test: /version endpoint returns 200 OK.
    '''
    response = client.get('/version')
    assert response.status_code == 200


@pytest.mark.unit
def test_version_endpoint_returns_version(client):
    '''
    Unit test: /version returns version string.
    '''
    response = client.get('/version')
    data = response.json

    assert 'version' in data
    assert isinstance(data['version'], str)
    assert len(data['version']) > 0

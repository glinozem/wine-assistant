import os
import pytest
import psycopg2
from flask import Flask

# Import your Flask app
import sys

sys.path.insert(0, os.path.abspath('.'))
from api.app import app as flask_app


# =============================================================================
# Flask App Fixtures
# =============================================================================

@pytest.fixture(scope='session')
def app():
    '''
    Flask application fixture (session-scoped).
    Created once per test session.
    '''
    flask_app.config.update({
        'TESTING': True,
        'DEBUG': False,
    })
    yield flask_app


@pytest.fixture(scope='function')
def client(app):
    '''
    Flask test client fixture (function-scoped).
    Created for each test function.

    Usage:
        def test_health(client):
            response = client.get('/health')
            assert response.status_code == 200
    '''
    return app.test_client()


# =============================================================================
# Database Fixtures
# =============================================================================

@pytest.fixture(scope='function')
def db_connection():
    '''
    PostgreSQL connection fixture (function-scoped with auto-rollback).
    Creates fresh connection for each test and rolls back changes.

    This ensures test isolation - changes made in one test don't affect others.

    Usage:
        def test_query(db_connection):
            cur = db_connection.cursor()
            cur.execute('SELECT 1')
            assert cur.fetchone()[0] == 1
    '''
    conn = psycopg2.connect(
        host=os.getenv('PGHOST', '127.0.0.1'),
        port=int(os.getenv('PGPORT', '5432')),
        user=os.getenv('PGUSER', 'postgres'),
        password=os.getenv('PGPASSWORD', 'postgres'),
        dbname=os.getenv('PGDATABASE', 'wine_db'),
    )
    # Disable autocommit to enable rollback
    conn.autocommit = False

    yield conn

    # Rollback any uncommitted changes after test
    try:
        conn.rollback()
    except Exception:
        pass  # Connection might be closed already
    finally:
        conn.close()


@pytest.fixture(scope='function')
def db_cursor(db_connection):
    '''
    Database cursor fixture (function-scoped).
    Auto-rollback after each test (no data pollution).

    Usage:
        def test_insert(db_cursor):
            db_cursor.execute('INSERT INTO products ...')
            # Automatically rolled back after test
    '''
    db_connection.autocommit = False
    cursor = db_connection.cursor()
    yield cursor
    db_connection.rollback()
    cursor.close()


# =============================================================================
# Environment Variables Fixtures
# =============================================================================

@pytest.fixture(scope='function')
def mock_env(monkeypatch):
    '''
    Mock environment variables fixture.

    Usage:
        def test_api_key(mock_env):
            mock_env('API_KEY', 'test_key_123')
            assert os.getenv('API_KEY') == 'test_key_123'
    '''

    def _set_env(key, value):
        monkeypatch.setenv(key, value)

    return _set_env


# =============================================================================
# Sample Data Fixtures
# =============================================================================

@pytest.fixture
def sample_product():
    '''
    Sample product data for testing.

    Usage:
        def test_product_creation(sample_product):
            assert sample_product['code'] == 'TEST001'
    '''
    return {
        'code': 'TEST001',
        'producer': 'Test Winery',
        'title_ru': 'Test Wine',
        'country': 'Italy',
        'region': 'Tuscany',
        'price_list_rub': 1000.0,
        'price_final_rub': 900.0,
    }


@pytest.fixture
def sample_csv_data():
    '''
    Sample CSV data for ETL testing.
    '''
    return '''code,producer,title_ru,price_rub
TEST001,Test Winery,Test Wine,1000
TEST002,Another Winery,Another Wine,1500'''

import re
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import stockwise_app as module


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db = module.DB_PATH
        module.DB_PATH = str(Path(self.temp.name) / 'test.db')
        module.app.config.update(TESTING=True)
        module.init_db()
        self.client = module.app.test_client()
        self.other = module.app.test_client()

    def tearDown(self):
        module.DB_PATH = self.old_db
        self.temp.cleanup()

    def token(self, client, path='/settings'):
        response = client.get(path)
        return re.search(r'name="csrf-token" content="([^"]+)"', response.text)[1]

    def post(self, client, path, data):
        data = dict(data, csrf_token=self.token(client, '/login' if path in ('/signup', '/login') else '/settings'))
        return client.post(path, data=data, follow_redirects=True)

    def signup(self, client, username):
        return self.post(client, '/signup', {'username': username, 'password': 'test-password'})

    def preferences(self, **overrides):
        return dict(section='preferences', theme='light', assistant_enabled='0', notifications_enabled='0', **overrides)

    def test_preferences_persist_and_are_isolated(self):
        self.assertEqual(self.client.get('/settings').status_code, 302)
        self.signup(self.client, 'alice')
        self.signup(self.other, 'bob')
        initial = self.client.get('/settings').text
        self.assertIn('data-theme="dark"', initial)
        self.assertIn('id = "chat-toggle"', initial)
        result = self.post(self.client, '/settings', self.preferences())
        self.assertIn('Changes saved successfully.', result.text)
        self.assertIn('data-theme="light"', result.text)
        self.assertNotIn('id = "chat-toggle"', result.text)
        self.assertNotIn('id = "chat-panel"', result.text)
        self.assertIn('data-theme="dark"', self.other.get('/settings').text)
        self.assertIn('id = "chat-toggle"', self.other.get('/dashboard').text)
        self.assertEqual(self.client.post('/chat/send', json={'history': []}, headers={'X-CSRF-Token': self.token(self.client)}).status_code, 403)
        self.assertEqual(self.client.get('/logout').status_code, 405)
        self.post(self.client, '/logout', {})
        self.assertEqual(self.client.get('/settings').status_code, 302)
        self.post(self.client, '/login', {'username': 'alice', 'password': 'test-password'})
        self.assertIn('data-theme="light"', self.client.get('/dashboard').text)
        self.post(self.client, '/settings', {'section': 'preferences', 'theme': 'dark', 'assistant_enabled': '1', 'notifications_enabled': '1'})
        self.assertIn('data-theme="dark"', self.client.get('/dashboard').text)
        self.assertIn('id = "chat-toggle"', self.client.get('/dashboard').text)
        with patch.object(module.ai, 'get_ai_reply', return_value='Test reply'), patch.object(module.user_context, 'build_budget_context', return_value=''), patch.object(module.user_context, 'build_stock_context', return_value=''):
            reply = self.client.post('/chat/send', json={'history': [{'role': 'user', 'content': 'Hello'}]}, headers={'X-CSRF-Token': self.token(self.client)})
            self.assertEqual(reply.json, {'reply': 'Test reply'})

    def test_profile_validation_and_login(self):
        self.signup(self.client, 'alice')
        self.signup(self.other, 'bob')
        for username in ('', 'x' * 81, 'bad\x01name'):
            self.assertIn('Username must contain', self.post(self.client, '/settings', {'section': 'profile', 'username': username}).text)
        self.assertIn('already taken', self.post(self.client, '/settings', {'section': 'profile', 'username': 'bob'}).text)
        self.assertIn('Signed in as alice', self.client.get('/settings').text)
        updated = self.post(self.client, '/settings', {'section': 'profile', 'username': ' alice-new ', 'user_id': 2})
        self.assertIn('Signed in as alice-new', updated.text)
        self.assertIn('Signed in as bob', self.other.get('/settings').text)
        self.post(self.client, '/logout', {})
        self.assertIn('Invalid username or password', self.post(self.client, '/login', {'username': 'alice', 'password': 'test-password'}).text)
        self.assertIn('Your Dashboard', self.post(self.client, '/login', {'username': 'alice-new', 'password': 'test-password'}).text)

    def test_password_changes_and_combined_profile_update(self):
        self.signup(self.client, 'alice')
        self.signup(self.other, 'bob')
        for username, current, new in (('alice', 'test-password', 'x'), ('alice-new', 'x', ' ')):
            result = self.post(self.client, '/settings', {
                'section': 'profile', 'username': username,
                'current_password': current, 'new_password': new,
                'confirm_password': new, 'user_id': 2,
            })
            self.assertIn('Changes saved successfully.', result.text)
            self.assertIn('Signed in as ' + username, result.text)
            self.assertEqual(self.client.get('/dashboard').status_code, 200)
            conn = module.get_db()
            saved = conn.execute('SELECT password_hash FROM users WHERE username = ?', (username,)).fetchone()[0]
            conn.close()
            self.assertNotEqual(saved, new)
            self.assertTrue(module.check_password_hash(saved, new))
            self.post(self.client, '/logout', {})
            self.assertIn('Invalid username or password', self.post(self.client, '/login', {'username': username, 'password': current}).text)
            self.assertIn('Your Dashboard', self.post(self.client, '/login', {'username': username, 'password': new}).text)
        self.post(self.other, '/logout', {})
        self.assertIn('Your Dashboard', self.post(self.other, '/login', {'username': 'bob', 'password': 'test-password'}).text)

    def test_invalid_password_changes_do_not_update_profile(self):
        self.signup(self.client, 'alice')
        self.signup(self.other, 'bob')
        cases = [
            ('wrong', 'x', 'x', 'Current password is incorrect.'),
            ('test-password', 'x', 'y', 'New passwords do not match.'),
            ('', 'x', 'x', 'fill in all three password fields'),
            ('test-password', '', '', 'fill in all three password fields'),
            ('test-password', 'x', '', 'fill in all three password fields'),
        ]
        for current, new, confirm, error in cases:
            result = self.post(self.client, '/settings', {
                'section': 'profile', 'username': 'changed',
                'current_password': current, 'new_password': new,
                'confirm_password': confirm,
            })
            self.assertIn(error, result.text)
            self.assertIn('Signed in as alice', result.text)
        duplicate = self.post(self.client, '/settings', {
            'section': 'profile', 'username': 'bob', 'current_password': 'test-password',
            'new_password': 'x', 'confirm_password': 'x',
        })
        self.assertIn('already taken', duplicate.text)
        self.post(self.client, '/logout', {})
        self.assertIn('Your Dashboard', self.post(self.client, '/login', {'username': 'alice', 'password': 'test-password'}).text)

    def test_csrf_and_invalid_preferences(self):
        self.signup(self.client, 'alice')
        for path in ('/settings', '/logout', '/transactions/add', '/budget-settings'):
            self.assertEqual(self.client.post(path, data={'section': 'preferences'}).status_code, 400)
        self.assertEqual(self.client.post('/chat/send', json={}).status_code, 400)
        foreign_token = self.token(self.other, '/login')
        self.assertEqual(self.client.post('/settings', data={'csrf_token': foreign_token}).status_code, 400)
        for field, value in (('theme', 'pink'), ('assistant_enabled', 'yes'), ('notifications_enabled', 'yes')):
            data = self.preferences()
            data[field] = value
            self.assertEqual(self.post(self.client, '/settings', data).status_code, 400)

    def test_navigation_transactions_and_budget_notifications(self):
        self.signup(self.client, 'alice')
        for path in ('/dashboard', '/transactions/add', '/budget-settings', '/stocks/search', '/articles'):
            with patch.object(module.stocks_data, 'get_search', return_value=[]):
                page = self.client.get(path)
            self.assertEqual(page.status_code, 200)
            self.assertIn('User Settings', page.text)
        self.post(self.client, '/transactions/add', {'name': 'Lunch', 'amount': '90', 'category': 'Food', 'date': module.date.today().isoformat()})
        conn = module.get_db()
        category = conn.execute("SELECT id FROM categories WHERE name = 'Food'").fetchone()[0]
        txn = conn.execute('SELECT id FROM transactions').fetchone()[0]
        conn.close()
        self.post(self.client, '/budget-settings', {f'limit_{category}': '100'})
        self.assertIn("close to your Food budget", self.client.get('/dashboard').text)
        self.post(self.client, '/settings', self.preferences())
        dashboard = self.client.get('/dashboard').text
        self.assertNotIn('close to your Food budget', dashboard)
        self.assertIn('Lunch', dashboard)
        self.assertIn('Monthly Budget Progress', dashboard)
        self.post(self.client, f'/transactions/{txn}/edit', {'name': 'Dinner', 'amount': '95', 'category': 'Food', 'date': module.date.today().isoformat()})
        self.assertIn('Dinner', self.client.get('/dashboard').text)
        self.post(self.client, f'/transactions/{txn}/delete', {})
        self.assertNotIn('Dinner', self.client.get('/dashboard').text)
        with patch.object(module.stocks_data, 'gainers_losers_mostactive', return_value=[]):
            self.assertEqual(self.client.get('/stocks/movers').status_code, 200)
        with patch.object(module.stocks_data, 'get_company_profile', return_value={'name': 'Test', 'symbol': 'TEST', 'sector': '', 'industry': '', 'website': '', 'description': ''}), patch.object(module.stocks_data, 'get_history', return_value=None), patch.object(module.stocks_data, 'get_roi_and_risk', return_value=None):
            self.assertEqual(self.client.get('/stocks/TEST').status_code, 200)

    def test_additive_migration_on_legacy_database(self):
        conn = sqlite3.connect(module.DB_PATH)
        conn.execute('DROP TABLE users')
        conn.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL)')
        conn.execute("INSERT INTO users VALUES (1, 'legacy', 'unchanged-hash', '2026-01-01')")
        conn.commit()
        conn.close()
        module.init_db()
        module.init_db()
        conn = module.get_db()
        user = conn.execute('SELECT * FROM users').fetchone()
        self.assertEqual((user['username'], user['password_hash'], user['theme'], user['assistant_enabled'], user['notifications_enabled']), ('legacy', 'unchanged-hash', 'dark', 1, 1))
        conn.close()


if __name__ == '__main__':
    unittest.main()

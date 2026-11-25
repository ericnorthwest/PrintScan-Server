import tempfile
import unittest
from pathlib import Path

from printscan_server.database import (
    clear_login_failures,
    create_session,
    create_user,
    delete_session,
    get_session,
    get_user,
    init_database,
    is_rate_limited,
    record_login_failure,
)
from printscan_server.security import hash_password


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "test.sqlite3"
        init_database(self.database_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_user_and_session_lifecycle(self):
        create_user(self.database_path, "tester", hash_password("long enough test password"))
        user = get_user(self.database_path, "TESTER")
        self.assertIsNotNone(user)
        token, csrf, _ = create_session(self.database_path, user["id"], 3600)
        session = get_session(self.database_path, token)
        self.assertEqual(session["username"], "tester")
        self.assertEqual(session["csrf_token"], csrf)
        delete_session(self.database_path, session["token_hash"])
        self.assertIsNone(get_session(self.database_path, token))

    def test_login_throttle_can_be_cleared(self):
        for _ in range(10):
            record_login_failure(self.database_path, "127.0.0.1")
        self.assertTrue(is_rate_limited(self.database_path, "127.0.0.1"))
        clear_login_failures(self.database_path, "127.0.0.1")
        self.assertFalse(is_rate_limited(self.database_path, "127.0.0.1"))


if __name__ == "__main__":
    unittest.main()

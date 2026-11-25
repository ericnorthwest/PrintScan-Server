import unittest

from printscan_server.security import hash_password, verify_password


class PasswordTests(unittest.TestCase):
    def test_hash_and_verify(self):
        password = "correct horse battery staple"
        encoded = hash_password(password)
        self.assertNotEqual(encoded, password)
        self.assertTrue(verify_password(password, encoded))
        self.assertFalse(verify_password("incorrect password", encoded))

    def test_hash_uses_random_salt(self):
        password = "correct horse battery staple"
        self.assertNotEqual(hash_password(password), hash_password(password))

    def test_short_password_is_rejected(self):
        with self.assertRaises(ValueError):
            hash_password("too-short")


if __name__ == "__main__":
    unittest.main()

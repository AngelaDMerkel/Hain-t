import unittest

from release_tools.next_version import Version, next_version


class AutomaticVersionTests(unittest.TestCase):
    def test_starts_at_repository_version_without_tags(self):
        self.assertEqual(next_version("1.0.0", [], []), Version(1, 0, 0))

    def test_increments_latest_patch(self):
        self.assertEqual(
            next_version("1.0.0", ["v1.0.0", "v1.0.2", "not-a-version"], []),
            Version(1, 0, 3),
        )

    def test_repository_version_is_release_floor(self):
        self.assertEqual(next_version("2.0.0", ["v1.9.9"], []), Version(2, 0, 0))

    def test_rerun_reuses_version_already_tagged_at_commit(self):
        self.assertEqual(
            next_version("1.0.0", ["v1.0.0", "v1.0.1"], ["v1.0.1"]),
            Version(1, 0, 1),
        )


if __name__ == "__main__":
    unittest.main()

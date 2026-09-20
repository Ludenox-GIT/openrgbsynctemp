import json
import os
import re
import unittest

MANIFEST_PATH = os.path.join(os.path.dirname(__file__), '..', 'third_party', 'dependencies.lock.json')

class TestDependencyManifest(unittest.TestCase):
    def setUp(self):
        self.manifest_file = os.path.normpath(MANIFEST_PATH)
        self.assertTrue(os.path.exists(self.manifest_file), f'Manifest not found at {self.manifest_file}')
        with open(self.manifest_file, 'r', encoding='utf-8') as f:
            self.data = json.load(f)

    def test_manifest_structure(self):
        self.assertIn('schema_version', self.data)
        self.assertEqual(self.data['schema_version'], 1)
        self.assertIn('artifacts', self.data)
        self.assertIsInstance(self.data['artifacts'], list)
        self.assertGreater(len(self.data['artifacts']), 0)

    def test_required_fields_and_uniqueness(self):
        required_fields = {
            'name', 'version', 'source_url', 'commit_or_tag',
            'size_bytes', 'sha256', 'license', 'source_archive_sha256'
        }
        seen_names = set()
        hex_pattern = re.compile(r'^[a-fA-F0-9]{64}$')

        for item in self.data['artifacts']:
            name = item.get('name')
            self.assertIsNotNone(name, 'Artifact must have name')
            self.assertNotIn(name, seen_names, f'Duplicate artifact name: {name}')
            seen_names.add(name)

            for field in required_fields:
                self.assertIn(field, item, f'Artifact {name} missing required field {field}')

            # Prohibited floating tags/versions
            version = str(item['version']).lower()
            source_url = str(item['source_url']).lower()
            self.assertNotIn(version, ['latest', '*', 'master', 'main'], f'Floating version in {name}')
            self.assertNotIn('/latest/', source_url, f'Floating URL in {name}')

            # Check sha256 format: either 64-char hex or explicit blocked/unverified gate
            sha = item['sha256']
            if sha.startswith('GATE_'):
                self.assertTrue(len(sha) > 5)
            else:
                self.assertTrue(hex_pattern.match(sha), f'Artifact {name} sha256 invalid: {sha}')

            src_sha = item['source_archive_sha256']
            if src_sha.startswith('GATE_'):
                self.assertTrue(len(src_sha) > 5)
            else:
                self.assertTrue(hex_pattern.match(src_sha), f'Artifact {name} source sha256 invalid: {src_sha}')

    def test_staged_vendor_files_match_manifest(self):
        # If any file exists under vendor/ matching an artifact, verify its hash
        vendor_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'vendor'))
        if not os.path.exists(vendor_dir):
            return

        import hashlib
        hex_pattern = re.compile(r'^[a-fA-F0-9]{64}$')
        for item in self.data['artifacts']:
            filename = item.get('filename')
            if filename:
                filepath = os.path.join(vendor_dir, filename)
                if os.path.exists(filepath):
                    with open(filepath, 'rb') as f:
                        digest = hashlib.sha256(f.read()).hexdigest().lower()
                    expected = item['sha256'].lower()
                    if hex_pattern.match(expected):
                        self.assertEqual(digest, expected, f'Staged file {filename} hash mismatch')

if __name__ == '__main__':
    unittest.main()

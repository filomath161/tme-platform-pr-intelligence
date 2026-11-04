import unittest
from parser import parse_changed_path
class ParserTests(unittest.TestCase):
    def test_dev(self):
        p=parse_changed_path('mft/dev/dev_nokia_config.yml'); self.assertEqual((p['service'],p['environment'],p['application']),('mft','dev','nokia'))
    def test_underscored_app(self):
        p=parse_changed_path('backup/prod/prod_billing_api_config.yaml'); self.assertEqual(p['application'],'billing api')
    def test_mismatched_env(self): self.assertIsNone(parse_changed_path('mft/prod/dev_nokia_config.yml'))
    def test_non_config(self): self.assertIsNone(parse_changed_path('.github/CODEOWNERS'))
if __name__=='__main__': unittest.main()

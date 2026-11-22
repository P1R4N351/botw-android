"""The README's Support section and .github/FUNDING.yml name the same donation targets.

The badge at the head of the README links to a '## Support' heading; the Bitcoin address shown there must be the one
GitHub's Sponsor button reads from FUNDING.yml; and FUNDING.yml lists exactly the two targets, nothing else.

DONATION_TEST_FAULT=<name> runs the checks against an in-memory faulted copy instead of the files (fault validation:
the tree is never modified). Names: no_heading, no_badge, wrong_address, extra_target."""
import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / 'README.md'
FUNDING = ROOT / '.github/FUNDING.yml'

BITCOIN = 'bc1q4a3lqcg87rvw7vxulausdqhhuwkwwa6w6v4mxx'
TARGETS = ['bitcoin:' + BITCOIN, 'https://www.rinnegatamante.eu/vitadb/#/user/PiSCES']
BADGE = re.compile(r'^\[!\[Support with Bitcoin\]\([^)]+\)\]\(#support\)$', re.M)
ADDRESS = re.compile(r'\bbc1[02-9ac-hj-np-z]{8,87}\b')
CUSTOM = re.compile(r'^custom:\s*\[(.*)\]\s*$', re.M)
ITEM = re.compile(r"'([^']*)'|\"([^\"]*)\"")


def _apply_fault(readme, funding):
    fault = os.environ.get('DONATION_TEST_FAULT', '')
    if fault == 'no_heading':
        readme = readme.replace('\n## Support\n', '\n## Donations\n', 1)
    elif fault == 'no_badge':
        readme = readme.replace('](#support)', '](#credits)', 1)
    elif fault == 'wrong_address':
        funding = funding.replace(BITCOIN, BITCOIN[:-1] + 'q', 1)
    elif fault == 'extra_target':
        funding = funding.replace("]", ", 'https://example.invalid/']", 1)
    elif fault:
        raise ValueError(f'unknown DONATION_TEST_FAULT {fault!r}')
    return readme, funding


def _funding_targets(funding):
    found = CUSTOM.findall(funding)
    if len(found) != 1:
        return None
    return [a or b for a, b in ITEM.findall(found[0])]


class DonationLinks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.readme, cls.funding = _apply_fault(README.read_text(encoding='utf-8'),
                                               FUNDING.read_text(encoding='utf-8'))

    def test_badge_links_to_a_support_heading(self):
        self.assertRegex(self.readme, BADGE)
        self.assertRegex(self.readme, re.compile(r'^## Support$', re.M))

    def test_funding_lists_exactly_the_two_targets(self):
        self.assertEqual(_funding_targets(self.funding), TARGETS)

    def test_readme_bitcoin_address_is_the_funding_one(self):
        section = self.readme.split('\n## Support\n', 1)
        self.assertEqual(len(section), 2, 'no ## Support section')
        body = section[1].split('\n## ', 1)[0]
        in_readme = sorted(set(ADDRESS.findall(body)))
        in_funding = sorted({t[len('bitcoin:'):] for t in _funding_targets(self.funding) or []
                             if t.startswith('bitcoin:')})
        self.assertEqual(len(in_readme), 1, in_readme)
        self.assertEqual(in_readme, in_funding)


if __name__ == '__main__':
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path

from validate_candidates import validate_editorial_input, _sha256


def make_files(root, *, replay=None, audit=None):
    (root / 'content' / '发现').mkdir(parents=True)
    (root / 'content' / '复核').mkdir(parents=True)
    audit_path = root / 'content' / '发现' / '2026-09-02.json'
    audit_path.write_text(json.dumps(audit or {'schema': 'daily-discovery-v1'}, ensure_ascii=False), encoding='utf-8')
    replay_path = root / 'content' / '复核' / '2026-09-02.json'
    if replay is not None:
        replay_path.write_text(json.dumps(replay, ensure_ascii=False), encoding='utf-8')
    return audit_path, replay_path


def base_replay(audit_path, replay_path, event_ids=('event-1',)):
    events = [
        {
            'eventId': event_id,
            'evidenceTierAfterUpgrade': 'A',
            'evidenceSources': [{'url': 'https://example.com/article', 'tier': 'A'}],
        }
        for event_id in event_ids
    ]
    return {
        'schema': 'daily-editorial-replay-v1',
        'date': '2026-09-02',
        'baseDiscoveryAuditPath': 'content/发现/2026-09-02.json',
        'baseDiscoveryAuditSha256': _sha256(audit_path),
        'discoveryAuditUnchanged': True,
        'queryAudits': [{
            'queryFamily': 'runtime-enrichment',
            'actualQuery': 'museum policy',
            'executedAt': '2026-09-02T17:00:00+08:00',
            'success': True,
            'returnedResultCount': 1,
            'acceptedRawCount': 1,
        }],
        'evidenceQualification': {'status': 'completed', 'attemptedEvents': len(events)},
        'finalEditorialPool': {
            'canonicalUniqueEvents': len(events),
            'editoriallyReviewed': len(events),
            'events': events,
        },
    }


class EditorialReplayContractTests(unittest.TestCase):
    def test_normal_production_uses_discovery_audit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit_path, _ = make_files(root)
            payload = {
                'date': '2026-09-02',
                'discoveryAuditPath': 'content/发现/2026-09-02.json',
            }
            errors, pool_ids = validate_editorial_input(root / 'content/候选/2026-09-02.json', payload, root)
            self.assertEqual(errors, [])
            self.assertIsNone(pool_ids)

    def test_revision_uses_only_replay_pool(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit_path, replay_path = make_files(root)
            payload = {
                'date': '2026-09-02',
                'discoveryAuditPath': 'content/发现/2026-09-02.json',
                'editorialInputPath': 'content/复核/2026-09-02.json',
                'revision': {
                    'revisionType': 'same_day_editorial_revision',
                    'discoveryAuditUnchanged': True,
                    'editorialInputPath': 'content/复核/2026-09-02.json',
                },
            }
            replay = base_replay(audit_path, replay_path)
            replay_path.write_text(json.dumps(replay, ensure_ascii=False), encoding='utf-8')
            errors, pool_ids = validate_editorial_input(root / 'content/候选/2026-09-02.json', payload, root)
            self.assertEqual(errors, [])
            self.assertEqual(pool_ids, {'event-1'})

    def test_revision_candidate_outside_replay_pool_is_rejected_by_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit_path, replay_path = make_files(root)
            replay = base_replay(audit_path, replay_path, ('event-1',))
            replay_path.write_text(json.dumps(replay, ensure_ascii=False), encoding='utf-8')
            payload = {
                'date': '2026-09-02',
                'discoveryAuditPath': 'content/发现/2026-09-02.json',
                'editorialInputPath': 'content/复核/2026-09-02.json',
                'revision': {'revisionType': 'same_day_editorial_revision', 'discoveryAuditUnchanged': True},
            }
            errors, pool_ids = validate_editorial_input(root / 'content/候选/2026-09-02.json', payload, root)
            self.assertEqual(errors, [])
            self.assertNotIn('event-2', pool_ids)

    def test_revision_requires_one_explicit_editorial_input(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit_path, replay_path = make_files(root)
            replay_path.write_text(json.dumps(base_replay(audit_path, replay_path), ensure_ascii=False), encoding='utf-8')
            payload = {
                'date': '2026-09-02',
                'discoveryAuditPath': 'content/发现/2026-09-02.json',
                'revision': {
                    'revisionType': 'same_day_editorial_revision',
                    'discoveryAuditUnchanged': True,
                    'editorialInputPath': 'content/复核/2026-09-02.json',
                },
            }
            errors, _ = validate_editorial_input(root / 'content/候选/2026-09-02.json', payload, root)
            self.assertIn('same_day_editorial_revision needs an explicit editorialInputPath', errors)

    def test_revision_rejects_parallel_editorial_input_reference(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit_path, replay_path = make_files(root)
            replay_path.write_text(json.dumps(base_replay(audit_path, replay_path), ensure_ascii=False), encoding='utf-8')
            payload = {
                'date': '2026-09-02',
                'discoveryAuditPath': 'content/发现/2026-09-02.json',
                'editorialInputPath': 'content/复核/2026-09-02.json',
                'revision': {
                    'revisionType': 'same_day_editorial_revision',
                    'discoveryAuditUnchanged': True,
                    'editorialInputPath': 'content/复核/another-pool.json',
                },
            }
            errors, _ = validate_editorial_input(root / 'content/候选/2026-09-02.json', payload, root)
            self.assertIn('revision editorialInputPath disagrees with ledger', errors)

    def test_replay_base_hash_and_identity_are_required(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit_path, replay_path = make_files(root)
            replay = base_replay(audit_path, replay_path)
            replay['baseDiscoveryAuditSha256'] = 'wrong'
            replay['discoveryAuditUnchanged'] = False
            replay_path.write_text(json.dumps(replay, ensure_ascii=False), encoding='utf-8')
            payload = {
                'date': '2026-09-02',
                'discoveryAuditPath': 'content/发现/2026-09-02.json',
                'editorialInputPath': 'content/复核/2026-09-02.json',
                'revision': {'revisionType': 'same_day_editorial_revision', 'discoveryAuditUnchanged': True},
            }
            errors, _ = validate_editorial_input(root / 'content/候选/2026-09-02.json', payload, root)
            self.assertIn('editorial replay baseDiscoveryAuditSha256 does not match immutable discovery audit', errors)
            self.assertIn('editorial replay must declare discoveryAuditUnchanged=true', errors)

    def test_historical_editorial_correction_uses_one_replay_pool(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit_path, replay_path = make_files(root)
            replay = base_replay(audit_path, replay_path)
            replay['revisionType'] = 'historical_editorial_correction'
            replay['replayReason'] = 'confirmed editorial false negative'
            replay_path.write_text(json.dumps(replay, ensure_ascii=False), encoding='utf-8')
            payload = {
                'date': '2026-09-02',
                'discoveryAuditPath': 'content/发现/2026-09-02.json',
                'editorialInputPath': 'content/复核/2026-09-02.json',
                'revision': {
                    'revisionType': 'historical_editorial_correction',
                    'discoveryAuditUnchanged': True,
                    'editorialInputPath': 'content/复核/2026-09-02.json',
                },
            }
            errors, pool_ids = validate_editorial_input(root / 'content/候选/2026-09-02.json', payload, root)
            self.assertEqual(errors, [])
            self.assertEqual(pool_ids, {'event-1'})

    def test_unknown_revision_type_cannot_open_parallel_pool(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit_path, replay_path = make_files(root)
            replay_path.write_text(json.dumps(base_replay(audit_path, replay_path), ensure_ascii=False), encoding='utf-8')
            payload = {
                'date': '2026-09-02',
                'discoveryAuditPath': 'content/发现/2026-09-02.json',
                'editorialInputPath': 'content/复核/2026-09-02.json',
                'revision': {'revisionType': 'unknown_revision', 'discoveryAuditUnchanged': True},
            }
            errors, _ = validate_editorial_input(root / 'content/候选/2026-09-02.json', payload, root)
            self.assertTrue(any('same_day_editorial_revision or historical_editorial_correction' in error for error in errors))


if __name__ == '__main__':
    unittest.main()

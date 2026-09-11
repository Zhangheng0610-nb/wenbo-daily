import json
import tempfile
import unittest
from pathlib import Path
from automation.recruitment_review import review_signature, apply_review_decisions
from automation.recruitment_discovery import persistent_review_queue, build_candidate

class RecruitmentReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.folder = self.root / 'content/招聘'
        (self.folder / '发现').mkdir(parents=True)
        self.row = build_candidate({'title':'某博物馆2026年8月招聘讲解员','url':'https://example.org/notice','deadline':'2026-08-31'})
        self.decision = {'signature':review_signature(self.row),'decision':'rejected','reason':'expired',
                         'evidence':[{'url':self.row['discoveryUrl']}],'reviewedAt':'2026-09-10T08:00:00+08:00'}
        self.save()
    def save(self):
        (self.folder/'review-decisions.json').write_text(json.dumps({'decisions':[self.decision]}),encoding='utf-8')
    def test_resolved_lead_does_not_resurrect_after_queue_rebuild(self):
        for day in ['2026-09-10','2026-09-11']:
            q=persistent_review_queue(self.root,{'date':day,'candidates':[self.row]})
            self.assertEqual(q['pendingCount'],0)
            self.assertEqual(q['appliedReviewCount'],1)
            (self.folder/'review-queue.json').write_text(json.dumps(q),encoding='utf-8')
    def test_changed_deadline_batch_role_code_section_or_application_reopens_review(self):
        for key,value in [('deadline','2026-10-01'),('recruitmentBatch','2026年9月'),('position','策展'),('positionCode','002'),('sourceSectionKey','notice-2'),('applicationHints',['new@example.org'])]:
            with self.subTest(key=key):
                q=persistent_review_queue(self.root,{'date':'2026-09-10','candidates':[{**self.row,key:value}]})
                self.assertEqual(q['pendingCount'],1)
    def test_observation_time_change_does_not_erase_decision(self):
        rows,applied=apply_review_decisions(self.root,[{**self.row,'lastSeen':'2026-09-11','discoveredAt':'later'}],'2026-09-11')
        self.assertEqual(rows[0]['decision'],'rejected')
    def test_future_decision_not_applied_to_historical_run(self):
        self.assertEqual(persistent_review_queue(self.root,{'date':'2026-09-09','candidates':[self.row]})['pendingCount'],1)
    def test_incomplete_decision_fails_loudly(self):
        del self.decision['evidence'];self.save()
        with self.assertRaises(ValueError):apply_review_decisions(self.root,[self.row],'2026-09-10')
    def test_review_file_cannot_publish_a_position(self):
        self.decision['decision']='included';self.save()
        with self.assertRaises(ValueError):apply_review_decisions(self.root,[self.row],'2026-09-10')
    def test_old_ledger_rejection_does_not_hide_extended_deadline(self):
        old={**self.row,'decision':'rejected'}
        (self.folder/'发现/2026-09-08.json').write_text(json.dumps({'date':'2026-09-08','candidates':[old]}),encoding='utf-8')
        # Batch is fixed: identity changes only when deadline changes; hints can
        # change without identity changing, and must also invalidate rejection.
        new={**self.row,'deadlineHints':['报名延期至2026年10月1日']}
        q=persistent_review_queue(self.root,{'date':'2026-09-10','candidates':[new]})
        self.assertEqual(q['pendingCount'],1)

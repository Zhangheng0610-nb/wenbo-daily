import unittest
from datetime import date
from unittest.mock import Mock, patch
from automation.daily_discovery import editorial_priority, evaluate_candidate_pool, international_heritage_signals
from automation.supply_recovery import recovery_plan, execute_recovery

class RecoveryTests(unittest.TestCase):
    def preview(self, scopes):
        return {'queryFamilies': [], 'candidateEvaluation': {'finalEditorialPool': {'events': [{'scope': s} for s in scopes]}}}

    def test_thin_supply_triggers_both_scopes(self):
        plan = recovery_plan(self.preview(['domestic']))
        self.assertTrue(plan['required'])
        self.assertEqual(set(plan['scopes']), {'domestic', 'international'})
        self.assertFalse(plan['publicationQuota'])

    def test_missing_scope_gets_targeted_recovery(self):
        self.assertEqual(recovery_plan(self.preview(['domestic'] * 7))['scopes'], ['international'])
        self.assertFalse(recovery_plan(self.preview(['domestic'] * 3 + ['international'] * 3))['required'])

    def test_failed_search_is_preserved_without_losing_other_results(self):
        calls = Mock(side_effect=[RuntimeError('timeout'), ([{'title': 'lead'}], {'success': True}), ([], {'success': True}), ([], {'success': True})])
        records, audits = execute_recovery(date(2026,9,7), {'scopes':['international']}, [{'id':'test'}], calls)
        self.assertEqual(len(audits), 4)
        self.assertEqual(len(records), 1)
        self.assertEqual(sum(a['success'] for a in audits), 3)
        self.assertTrue(any('timeout' in a.get('failure', '') for a in audits))

    def test_professional_english_signals_survive_three_day_window(self):
        for title in (
            'Heritage Resilience in Congo: Government action with Heritage Emergency Fund',
            'Documentary Heritage Professionals Receive Memory of the World Prize',
            'Archaeological excavation reveals new findings at a coastal site',
            'Museum launches digital preservation of endangered manuscripts',
        ):
            row = {'title': title, 'publishedDate':'2026-09-04', 'url':'https://www.unesco.org/en/articles/example', 'scope':'international'}
            result = evaluate_candidate_pool(date(2026,9,7), [row], previous_rejections=[])['records'][0]
            self.assertNotEqual(result['candidateDisposition'], 'deferred', title)
            self.assertNotEqual(result['candidateDisposition'], 'rejected', title)
            self.assertTrue(international_heritage_signals(row), title)

    def test_general_education_media_and_climate_do_not_get_bonus(self):
        for title in ('Schools prepare for climate challenge with emergency fund',
                      'University wins digital media award',
                      'Ocean research prize celebrates new discoveries',
                      'Digital platforms advance media governance'):
            self.assertFalse(international_heritage_signals({'title':title}), title)

    def test_formal_run_recovery_flows_through_same_final_audit(self):
        from automation.daily_discovery import run
        first = self.preview(['domestic'])
        final = self.preview(['domestic', 'international'])
        with patch('automation.daily_discovery.SOURCE_SCANS', []), \
             patch('automation.daily_discovery.execute_queries', return_value=([{'title':'original'}], [])), \
             patch('automation.daily_discovery.load_fixed_panel_radar', return_value=([], {})), \
             patch('automation.daily_discovery.build_audit', side_effect=[first, final]) as build, \
             patch('automation.supply_recovery.execute_recovery', return_value=([{'title':'recovered'}], [{'success': True}])) as recover:
            result = run(date(2026,9,7))
        recover.assert_called_once()
        self.assertFalse(build.call_args_list[0].kwargs['perform_evidence_upgrade'])
        self.assertTrue(build.call_args_list[1].kwargs['perform_evidence_upgrade'])
        self.assertEqual([r['title'] for r in build.call_args_list[1].args[3]], ['original', 'recovered'])
        self.assertEqual(result['supplyRecovery']['qualifiedAfter'], 2)
        self.assertFalse(result['supplyRecovery']['targetMet'])
        self.assertEqual(len(result['queryFamilies']), 2)

    def test_source_prestige_does_not_create_professional_signal(self):
        self.assertFalse(international_heritage_signals({'title':'New educational programme', 'sourceDomain':'unesco.org'}))

if __name__ == '__main__':
    unittest.main()

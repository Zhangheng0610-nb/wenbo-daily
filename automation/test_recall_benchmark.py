import unittest
from automation.recall_benchmark import evaluate


class RecallBenchmarkTests(unittest.TestCase):
    def reference(self, **extra):
        return {'name':'fixture','events':[dict(id='one',title='Named event',scope='domestic',expected='review_candidate',titleAliases=['Named event'],urls=['https://source.test/a'],**extra)]}

    def test_shared_document_url_cannot_claim_recall(self):
        result=evaluate(self.reference(sharedDocument=True),{'records':[{'title':'Different event','url':'https://source.test/a'}]})
        self.assertEqual(result['events'][0]['stage'],'not_discovered')

    def test_report_identity_traces_shortened_candidate(self):
        event={'eventId':'a','title':'Short name','discoveryReports':[{'title':'Named event'}]}
        result=evaluate(self.reference(),{'records':[{'title':'Named event'}], 'candidateEvaluation':{'eventCandidates':[event],'pool':[{'eventId':'a'}],'finalEditorialPool':{'events':[{'eventId':'a'}]}}})
        self.assertEqual(result['events'][0]['stage'],'final_pool')

    def test_absent_ids_do_not_match_unrelated_candidates(self):
        result=evaluate(self.reference(),{'records':[{'title':'Named event'}],'candidateEvaluation':{'pool':[{'title':'Other'}]}})
        self.assertEqual(result['events'][0]['stage'],'before_candidate_pool')

    def test_history_suppression_is_visible(self):
        result=evaluate(self.reference(),{'records':[{'title':'Named event','duplicateStatus':'historical_duplicate','duplicateOfTitle':'Wrong old event'}]})
        self.assertEqual(result['events'][0]['duplicateTargets'],['Wrong old event'])
        self.assertFalse(result['events'][0]['expectationMet'])


if __name__=='__main__': unittest.main()

import unittest
from automation.editorial_policy import rejection_policy_issues


class EditorialPolicyTests(unittest.TestCase):
    def check(self,reason,**extra):
        return rejection_policy_issues(dict(decision='rejected',evidenceTier='A',dedupStatus='unique_event',decisionReason=reason,**extra))

    def test_actual_shared_url_and_publisher_quota_reasons_are_flagged(self):
        for text in ('日报校验要求同一来源 URL 不重复','为避免重复来源 URL，暂不入选','与其他事件存在来源 URL 复用', '为避免同源国际条目过密，暂不重复入选', '不把新闻列入五条日报'):
            self.assertTrue(self.check(text),text)

    def test_editorial_value_rejections_remain_valid(self):
        for text in ('会议报道未披露新的考古材料或制度变化','资金尚未落实，待核实项目阶段','仅为旧事评论，未提供新增事实'):
            self.assertFalse(self.check(text),text)

    def test_real_duplicate_and_unqualified_source_not_overridden(self):
        candidate={'decision':'rejected','evidenceTier':'A','dedupStatus':'historical_duplicate','decisionReason':'同一来源 URL 不重复'}
        self.assertFalse(rejection_policy_issues(candidate))
        candidate.update(dedupStatus='unique_event',evidenceTier='C')
        self.assertFalse(rejection_policy_issues(candidate))

    def test_deferred_context_check_is_not_forced_to_publish(self):
        self.assertFalse(rejection_policy_issues({'decision':'deferred','evidenceTier':'A','decisionReason':'需补充背景'}))


if __name__=='__main__': unittest.main()

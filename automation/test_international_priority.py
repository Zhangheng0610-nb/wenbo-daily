import unittest
from datetime import date
from automation.daily_discovery import editorial_priority, international_heritage_signals

class InternationalPriorityTests(unittest.TestCase):
    def score(self,title):
        return editorial_priority({'title':title,'publishedDate':'2026-09-07','scope':'international'},date(2026,9,8))

    def test_general_politics_cannot_take_museum_governance_priority(self):
        for title in ['Litigation Tracker: Legal Challenges to Trump Administration Actions',
                      'Proposed bill would bar taxpayer funding for AI surveillance cameras',
                      'Trump administration to end tax-exempt status over school discrimination',
                      'City administration changes tax collection rules']:
            self.assertNotIn('museum_or_cultural_institution_governance',self.score(title)['reasons'])

    def test_named_museum_keeps_priority_without_museum_word(self):
        for title in ['Smithsonian showdown intensifies as administration issues new warning',
                      'Rijksmuseum funding cuts announced',
                      'Advocates Demand the Parker Administration Repair Atwater Kent Building']:
            self.assertIn('museum_or_cultural_institution_governance',self.score(title)['reasons'])

    def test_repatriation_needs_objects_and_action(self):
        positive='Speed Art Museum completes first repatriation of Indigenous artifacts'
        self.assertGreaterEqual(self.score(positive)['score'],55)
        for title in ['Government announces repatriation of citizens',
                      'Museum essay debates repatriation of artifacts',
                      'Bronzes on display at museum']:
            self.assertNotIn('cultural_property_repatriation',international_heritage_signals({'title':title}))

    def test_discovery_inflection_and_cave_art(self):
        for title in ['Research team discovers ancient tomb',
                      '15,000-year-old cave art discovery could rewrite history']:
            self.assertGreaterEqual(self.score(title)['score'],55)
        self.assertNotIn('archaeological_new_knowledge',international_heritage_signals({'title':'Museum opens cave art photography exhibition'}))

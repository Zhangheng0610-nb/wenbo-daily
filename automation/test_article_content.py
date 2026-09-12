import base64
import gzip
import io
import random
import unittest
from unittest.mock import patch
from automation.article_content import article_content,article_citations
from automation.daily_discovery import visible_article_text,_fetch_evidence_url

class Response(io.BytesIO):
    def __init__(self,raw,url='https://www.news.cn/article.html',encoding='gzip'):
        super().__init__(raw);self.headers={'Content-Encoding':encoding};self.url=url
    def geturl(self):return self.url

class ArticleContentTests(unittest.TestCase):
    def test_article_excludes_unrelated_navigation_and_recommendations(self):
        page='<nav>某博物馆被盗</nav><article><h1>修复工程启动</h1><p>博物院正式启动壁画修复工程。</p><div class="recommended-features">某馆辞职</div><div class="more-to-discover">文物返还</div><p hidden>隐藏的重大考古发现</p></article><footer>博物馆拨款</footer>'
        body,scope,_=article_content(page)
        self.assertEqual(scope,'article');self.assertIn('壁画修复',body)
        for phrase in ['被盗','辞职','返还','隐藏','拨款']:self.assertNotIn(phrase,body)
    def test_plain_text_and_simple_article_remain_readable(self):
        self.assertEqual(visible_article_text('纯文本原文'),'纯文本原文')
        self.assertEqual(visible_article_text('<p>正文 A &amp; B</p>'),'正文 A & B')
    def test_citations_come_from_reporting_paragraph_not_subscription_links(self):
        page='<nav><a href="https://subscribe.example.org">Subscribe</a></nav><article><p>According to <a href="https://agency.example.org/news">Agency</a>, a tomb was found.</p><div class="related-posts"><p>A newspaper reports <a href="https://unrelated.example.org">another story</a></p></div></article>'
        refs=article_citations(page,'https://museum.example.org/a')
        self.assertEqual(len(refs),1);self.assertEqual(refs[0]['url'],'https://agency.example.org/news')
        self.assertEqual(refs[0]['status'],'unverified_citation')
    def test_gzip_evidence_is_not_truncated_at_old_256k_limit(self):
        padding=base64.b64encode(random.Random(24).randbytes(350000)).decode()
        raw=('<script>'+padding+'</script><article><h1>馆舍修复</h1><p>正文已完整读取。</p></article>').encode()
        packed=gzip.compress(raw);self.assertGreater(len(packed),256000)
        with patch('automation.daily_discovery.SEARCH_OPENER.open',return_value=Response(packed)):
            _,body,error=_fetch_evidence_url('https://www.news.cn/article.html')
        self.assertIsNone(error);self.assertEqual(visible_article_text(body),'馆舍修复 正文已完整读取。')
    def test_canonical_follow_uses_same_decoder(self):
        first=b'<link rel="canonical" href="https://www.news.cn/final.html"><p>redirect</p>'
        final='<article><p>规范地址的真实正文。</p></article>'.encode()
        with patch('automation.daily_discovery.SEARCH_OPENER.open',side_effect=[Response(gzip.compress(first)),Response(gzip.compress(final),'https://www.news.cn/final.html')]):
            url,body,error=_fetch_evidence_url('https://www.news.cn/article.html')
        self.assertIsNone(error);self.assertEqual(url,'https://www.news.cn/final.html');self.assertIn('真实正文',body)
    def test_broken_compression_returns_fetch_failure(self):
        with patch('automation.daily_discovery.SEARCH_OPENER.open',return_value=Response(b'not gzip')):
            _,body,error=_fetch_evidence_url('https://www.news.cn/article.html')
        self.assertEqual(body,'');self.assertTrue(error)

    def test_title_match_without_visible_body_never_verifies_official_article(self):
        from automation.daily_discovery import resolve_evidence_attempt
        title='某博物馆宣布启动文物修复工程'
        url='https://www.news.cn/article.html'
        page='<head><title>'+title+'</title></head><main></main>'
        event={'title':title,'representativeTitle':title,'publishedDate':'2026-09-12'}
        with patch('automation.daily_discovery.resolve_evidence_url',return_value=(url,page,None)):
            checked,publishable=resolve_evidence_attempt(event,{'title':title,'url':url},'direct')
        checked=checked['checked']
        self.assertFalse(checked['articleVerified']);self.assertIsNone(publishable)
        self.assertEqual(checked['failureClassification'],'empty_body')

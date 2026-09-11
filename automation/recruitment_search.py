"""Web search for vacancies, independent of the daily-news RSS backends."""
from urllib.request import Request
from urllib.parse import urlencode,urlsplit
from automation.daily_discovery import SEARCH_OPENER,SEARCH_USER_AGENT,_BingHtmlResultParser,actual_query,unwrap_redirect_url

BACKENDS=({'id':'bing-web','name':'Bing Web'},)


def execute_query(family,backend,query,start,end):
    from automation.recruitment_discovery import now_cn, keep_discovery_record
    actual=query if family['id'].endswith('open_ended') else actual_query(query,start,end)
    audit={'queryFamily':family['id'],'scope':family['scope'],'backend':backend['id'],'actualQuery':actual,'executedAt':now_cn(),'success':False,'acceptedRawCount':0,'returnedResultCount':0,'undatedResultCount':0,'failure':None}
    try:
        request=Request('https://www.bing.com/search?'+urlencode({'q':actual,'setlang':'zh-hans','count':20}),headers={'User-Agent':SEARCH_USER_AGENT,'Accept':'text/html'})
        with SEARCH_OPENER.open(request,timeout=12) as response:
            raw=response.read(2_000_001)
            if len(raw)>2_000_000:raise ValueError('oversized_search_response')
            html=raw.decode('utf-8',errors='replace')
            audit['httpStatus']=response.status
        parser=_BingHtmlResultParser();parser.feed(html)
        if not parser.results and not any(s in html for s in ('没有找到','There are no results','No results found')):raise ValueError('no_parseable_web_results')
        records=[]
        for item in parser.results:
            item['url']=unwrap_redirect_url(item['url'])[0]
            if urlsplit(item['url']).scheme not in ('http','https'):continue
            records.append({'title':item['title'],'url':item['url'],'snippet':item['snippet'],'publishedDate':'',
                'discoveredVia':'bing-web','discoverySourceType':'recruitment_web_search','discoveryQuery':actual,
                'queryFamily':family['id'],'queryBackend':backend['id'],'scope':family['scope'],
                'sourceDomain':urlsplit(item['url']).hostname or ''})
        relevant=[r for r in records if keep_discovery_record(r)]
        audit.update(success=bool(relevant) or not records,acceptedRawCount=len(relevant),returnedResultCount=len(records),undatedResultCount=len(relevant),irrelevantResultCount=len(records)-len(relevant))
        if records and not relevant:audit['failure']='no_recruitment_relevance_in_returned_results'
        return relevant,audit
    except Exception as exc:
        audit['failure']=f'{type(exc).__name__}: {str(exc)[:240]}'
        return [],audit

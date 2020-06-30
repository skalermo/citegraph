from typing import NewType, List, Dict, Optional, NamedTuple, Iterable

import grequests
import semanticscholar

import requests_cache
import concurrent.futures as futures

from citegraph.model import Biblio, Paper

PaperId = NewType("PaperId", str)

API_URL = 'http://api.semanticscholar.org/v1'



class PaperAndRefs(NamedTuple):
    paper: Paper
    references: List[Paper]
    citations: List[Paper]


    @property
    def id(self):
        return self.paper.id


    @property
    def in_degree(self):
        return len(self.citations)


    @property
    def out_degree(self):
        return len(self.references)


class PaperDb(object):
    # Cache requests made to semanticscholar, since they are idempotent
    # This is super important!
    requests_cache.install_cache(cache_name="semapi", backend='sqlite')


    def __init__(self, bibdata: Biblio):
        self.bibdata = bibdata
        self.memcache = {}

    def batch_fetch(self, ids: Iterable[PaperId], exhandler) -> List[PaperAndRefs]:
        # TODO parallelize
        res = []
        for id in ids:
            r = self.fetch_from_id(id)
            if r:
                res.append(r)
            else:
                exhandler(id, None)
        return res

        # fixme This is the parallel code, which unfortunately doesn't use caching

        requests = [PaperDb.__get_data("paper", id) for id in ids if id not in self.memcache]

        responses = grequests.map(requests, exception_handler=exhandler)

        results = [self.memcache[id] for id in ids if id in self.memcache]

        for r in responses:
            print(r)
            data = {}
            if r and r.status_code == 200:
                data = r.json()
                if len(data) == 1 and 'error' in data:
                    data = {}
            elif r and r.status_code == 429:
                raise ConnectionRefusedError('HTTP status 429 Too Many Requests.')

            if len(data) == 0:
                exhandler(r, None)
                continue

            paper = PaperAndRefs(paper=self.bibdata.make_entry(data),
                                 references=[self.bibdata.make_entry(ref) for ref in data["references"]],
                                 citations=[self.bibdata.make_entry(ref) for ref in data["citations"]]
                                 )
            self.memcache[paper.id] = paper
            results.append(paper)

        return results


    def fetch_from_id(self, paper_id: PaperId) -> Optional[PaperAndRefs]:
        """Returns an entry a"""
        if paper_id in self.memcache:
            return self.memcache[paper_id]

        paper_dict: Dict = semanticscholar.paper(paper_id)

        if len(paper_dict.keys()) == 0:
            result = None
        else:
            result = PaperAndRefs(paper=self.bibdata.make_entry(paper_dict),
                                  references=[self.bibdata.make_entry(ref) for ref in paper_dict["references"]],
                                  citations=[self.bibdata.make_entry(ref) for ref in paper_dict["citations"]]
                                  )
        self.memcache[paper_id] = result
        return result


    @staticmethod
    def __get_data(method, id, include_unknown_references=False) -> futures.Future:

        '''Get data from Semantic Scholar API

        :param method: 'paper' or 'author'.
        :param id: :class:`str`.
        :returns: data or empty :class:`dict` if not found.
        :rtype: :class:`dict`
        '''

        method_types = ['paper', 'author']
        if method not in method_types:
            raise ValueError('Invalid method type. Expected one of: {}'.format(method_types))

        url = '{}/{}/{}'.format(API_URL, method, id)
        if include_unknown_references:
            url += '?include_unknown_references=true'
        return grequests.get(url)

        #
        # if r.status_code == 200:
        #     data = r.json()
        #     if len(data) == 1 and 'error' in data:
        #         data = {}
        # elif r.status_code == 429:
        #     raise ConnectionRefusedError('HTTP status 429 Too Many Requests.')
        #
        # return data

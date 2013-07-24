from __future__ import division
import numpy as np
from numpy import log2, ceil
import abc
from collections import defaultdict, OrderedDict
from heapq import heappush, heappop, heapify
from itertools import izip, izip_longest, tee

from prob import FiniteRandomVariable

##########
#  util  #
##########

def blockify(seq,blocklen,fill=None):
    args = [iter(seq)]*blocklen
    return izip_longest(*args,fillvalue=fill)

def huffman(X):
    p = X.pmf

    queue = [(p(x),(x,),('',)) for x in X.range()]
    heapify(queue)

    while len(queue) > 1:
        p2, symbols1, codes1 = heappop(queue)
        p1, symbols2, codes2 = heappop(queue)
        heappush(queue, (p1+p2, symbols1+symbols2,
            ['0' + c for c in codes1] + ['1' + c for c in codes2]))

    _, symbols, codes = queue[0]
    return OrderedDict(sorted(zip(symbols, codes),key=lambda x: len(x[1])))

###########
#  codes  #
###########

# a code specifies a mapping from symbols to codewords

class Code(object):
    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def compress(self,seq):
        pass

    @abc.abstractmethod
    def decompress(self,bitstring):
        pass

# a model-based code corresponds to fitting a probabilistic model to data

class ModelBasedCode(Code):
    __metaclass__ = abc.ABCMeta

    @classmethod
    @abc.abstractmethod
    def fit(cls,seq,blocklen=1):
        pass

    @classmethod
    def fit_and_compress(cls,seq,blocklen=1):
        seq = list(blockify(seq,blocklen))
        code = cls.fit(seq)
        result = ''.join(code.compress(seq))

        print code

        N = len(seq)
        bits_per_input_symbol = ceil(log2(len(set(seq))))
        inbits = N*bits_per_input_symbol
        outbits = len(result)
        print '\n%s with block length %d achieved compression rate: %gx\n    (%g bits per raw symbol, %g compressed bits per symbol)\n' \
                % (cls.__name__, blocklen, outbits/inbits,
                        bits_per_input_symbol, outbits/N)

        return result

# an iid code is backed by an iid random variable model and a codebook

class IIDCode(ModelBasedCode):
    def __init__(self,codebook):
        self._codebook = codebook
        self._inv_codebook = {v:k for k,v in codebook.iteritems()}

    def compress(self,seq):
        return ''.join(self._codebook[s] for s in seq)

    def decompress(self,bits):
        bits = iter(bits)
        while True:
            yield self.consume_next(self._inv_codebook,bits)

    @staticmethod
    def consume_next(inv_codebook,bits):
        # NOTE: prefix-free is important here!
        bitbuf = ''
        for bit in bits:
            bitbuf += bit
            if bitbuf in inv_codebook:
                return inv_codebook[bitbuf]

    def __repr__(self):
        return '\n'.join('%s -> %s' % (symbol, code)
                for symbol, code in self._codebook.iteritems())

    @classmethod
    def fit(cls,seq):
        model = cls.estimate_iid_source(seq)
        return cls.from_rv(model)

    @classmethod
    def from_rv(cls,X):
        return cls(huffman(X))

    @staticmethod
    def estimate_iid_source(seq):
        counts = defaultdict(int)
        tot = 0
        for symbol in seq:
            counts[symbol] += 1
            tot += 1
        pmf = {symbol:count/tot for symbol, count in counts.iteritems()}
        return FiniteRandomVariable(pmf)

# a Markov code is backed by a Markov chain model and for each symbol it has a
# separate codebook to encode the next symbol
# TODO test all this
# TODO pass in alphabet to estimation methods

class MarkovCode(ModelBasedCode):
    def __init__(self,codebooks):
        # TODO just map symbol to IIDCode?
        self._codebooks = codebooks # dict of codebooks, indexed by alphabet
        self._firstcodebook = codebooks.values()[0] # convention
        self._inv_firstcodebook = {v:k for k,v in self._firstcodebook.iteritems()}
        self._inv_codebooks = {symbol:{v:k for k,v in codebook.iteritems()}
                for symbol,codebook in codebooks.iteritems()}

    def compress(self,seq):
        s1, s2 = tee(seq,2)
        firstsymbol = next(s2)
        return self._firstcodebook[firstsymbol] + \
                ''.join(self._codebooks[a][b] for a, b in izip(s1,s2))

    def decompress(self,bits):
        bits = iter(bits)
        symbol = IIDCode.consume_next(self._firstcodebook,bits)
        while True:
            yield symbol
            symbol = IIDCode.consume_next(self._inv_codebooks[symbol],bits)

    def __repr__(self):
        return '\n'.join('%s -> %s' % (symbol, code)
                for symbol, code in self._codebook.iteritems())

    @classmethod
    def fit(cls,seq):
        model = cls.estimate_markov_source(seq)
        return cls.from_markovchain(model)

    @classmethod
    def from_markovchain(cls,(symbols,P)):
        return cls({s:huffman(FiniteRandomVariable(dict(zip(symbols,dist))))
            for s,dist in zip(symbols,P)})

    @staticmethod
    def estimate_markov_source(seq):
        s1, s2 = tee(seq,2)
        next(s2)
        counts = defaultdict(lambda: defaultdict(int))
        tots = defaultdict(int)
        for a,b in izip(s1,s2):
            counts[a][b] += 1
            tots[a] += 1
        symbols = counts.keys()
        return (symbols, np.array([[counts[i][j]/tots[i] for j in symbols] for i in symbols]))

# TODO arithemetic codes: separate the model from the coding mechanism
# TDOO lempel-ziv


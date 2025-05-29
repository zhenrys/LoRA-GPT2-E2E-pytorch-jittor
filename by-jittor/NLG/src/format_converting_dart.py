#  ------------------------------------------------------------------------------------------
#  Copyright (c) Microsoft Corporation. All rights reserved.
#  Licensed under the MIT License (MIT). See LICENSE in the repo root for license information.
#  ------------------------------------------------------------------------------------------
import sys
import io
import json
import random

with open(sys.argv[1], 'r', encoding='utf8') as reader, \
     open(sys.argv[2], 'w', encoding='utf8') as writer :
    lines_dict = json.load(reader)

    full_rela_lst = []
    full_src_lst = []
    full_tgt_lst = []
    unique_src = 0

    for example in lines_dict:
        rela_lst = []
        temp_triples = ''
        for i, tripleset in enumerate(example['tripleset']):
            subj, rela, obj = tripleset
            rela = rela.lower()
            rela_lst.append(rela)
            if i > 0:
                temp_triples += ' | '
            temp_triples += '{} : {} : {}'.format(subj, rela, obj)

        unique_src += 1

        for sent in example['annotations']:
            full_tgt_lst.append(sent['text'])
            full_src_lst.append(temp_triples)
            full_rela_lst.append(rela_lst)

    print('unique source is', unique_src)
    lst=zip(full_src_lst, full_tgt_lst)
    num=0
    S=dict()
    MAXN=len(full_src_lst)/100
    random.seed(2025)

    while num<MAXN:
        idx = random.choice(range(0, len(full_src_lst)))
        src, tgt=full_src_lst[idx],full_tgt_lst[idx]
        if src in S.keys():continue
        S[src]=1
        x = {}
        x['context'] = src  # context #+ '||'
        x['completion'] = tgt  # completion
        writer.write(json.dumps(x) + '\n')
        num+=1
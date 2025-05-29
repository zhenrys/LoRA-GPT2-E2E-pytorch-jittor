#  ------------------------------------------------------------------------------------------
#  Copyright (c) Microsoft Corporation. All rights reserved.
#  Licensed under the MIT License (MIT). See LICENSE in the repo root for license information.
#  ------------------------------------------------------------------------------------------
import random
import sys
import io
import json


with open(sys.argv[1], 'r', encoding='utf8') as reader, \
     open(sys.argv[2], 'w', encoding='utf8') as writer :
    lines_dict = json.load(reader)

    full_rela_lst = []
    full_src_lst = []
    full_tgt_lst = []
    full_cate_lst = []

    seen = [
        'Airport', 
        'Astronaut', 
        'Building', 
        'City', 
        'ComicsCharacter', 
        'Food', 
        'Monument', 
        'SportsTeam', 
        'University', 
        'WrittenWork'
    ]

    cate_dict = {}
    for i, example in enumerate(lines_dict['entries']):
        sents = example[str(i+1)]['lexicalisations']
        triples = example[str(i + 1)]['modifiedtripleset']
        cate = example[str(i + 1)]['category']

        if not cate in cate_dict:
            cate_dict[cate] = 0
        cate_dict[cate] += 1

        rela_lst = []
        temp_triples = ''
        for i, tripleset in enumerate(triples):
            subj, rela, obj = tripleset['subject'], tripleset['property'], tripleset['object']
            rela_lst.append(rela)
            if i > 0:
                temp_triples += ' | '
            temp_triples += '{} : {} : {}'.format(subj, rela, obj)

        for sent in sents:
            if sent["comment"] == 'good':
                full_tgt_lst.append(sent['lex'])
                full_src_lst.append(temp_triples)
                full_rela_lst.append(rela_lst)
                full_cate_lst.append(cate)

    for cate in cate_dict:
        print('cate', cate, cate_dict[cate])

    #edited_sents = []
    MAXN=len(full_src_lst)/100
    random.seed(123)
    lst=zip(full_src_lst, full_tgt_lst, full_cate_lst)
    num=0
    S=dict()
    while num<MAXN:
        idx=random.choice(range(0,len(full_src_lst)))

        src, tgt, cate=full_src_lst[idx],full_tgt_lst[idx],full_cate_lst[idx]
        if src in S.keys():continue
        S[src]=1
        x = {}
        x['context'] =  src # context #+ '||'
        x['completion'] = tgt #completion
        x['cate'] = cate in seen
        writer.write(json.dumps(x)+'\n')
        num+=1


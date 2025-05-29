

import sys
import json

with open(sys.argv[1], 'r', encoding='utf8') as reader, \
     open(sys.argv[2], 'w', encoding='utf8') as writer:
    line_count = 0
    for line in reader:
        items = line.strip().split('||')
        context = items[0]
        completion = items[1].strip('\n')
        x = {}
        x['context'] = context  # + '||'
        x['completion'] = completion
        writer.write(json.dumps(x) + '\n')
        line_count += 1

print(f"数据处理完成，总行数: {line_count}")


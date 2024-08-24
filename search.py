#!/usr/bin/env python
#-*- coding:utf-8 -*-


import json
import os
from fnmatch import fnmatch
from utilities import errorHandler

def do_search(options):
    # example:
    # --search From,"ds??hjk?uzbhj?hz@wildduck.*"
    #
    # options['search_filter'] schema for above example:
    # Keyword Comma "Value String"
    #
    # 1. find all metadata.json in options['local_folder']
    # 2. on each metadata.json
    # 3. check if key is an array or make it an array
    # 4. fnmatch each value
    # 5. if found, print path of metadata.json and metadata.json contents

    
    try:
        search_key, search_value = options['search_filter'].split(',', 1)
    except Exception as e:
        errorHandler(e, 'Invalid search filter (`Keyword,"fnmatch syntax"`)')

    print('Searching for {} = {}'.format(search_key, search_value))

    count = 0

    for root, dirs, files in os.walk(options['local_folder']):
        for file in files:
            if file == 'metadata.json':
                json_path = os.path.join(root, file)
                with open(json_path, 'r') as f:
                    json_content = json.load(f)
                    if search_key in json_content:
                        if isinstance(json_content[search_key], list):
                            json_values = json_content[search_key]
                        else:
                            json_values = [json_content[search_key]]

                        for json_value in json_values:
                            if fnmatch(str(json_value), search_value):
                                print('\n' + json_path)
                                print(json.dumps(json_content, indent=4))
                                count += 1
                                break
    
    errorHandler(count, 'Done', 0)
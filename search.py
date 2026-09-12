#!/usr/bin/env python
# -*- coding:utf-8 -*-


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
        output_by(options['search_output'], 'error', {'error': str(e)})

    output_by(options['search_output'], 'start', {'search_key': search_key, 'search_value': search_value})
    
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
                                output_by(options['search_output'], 'item', {'json_path': json_path, 'json_content': json_content, 'count': count})
                                count += 1
                                break
    
    output_by(options['search_output'], 'end', {'count': count})


def output_by(type, block, data):
    if type == 'json':
        if block == 'error':
            print(json.dumps({
                "error": 'Invalid search filter (`Keyword,"fnmatch syntax"`)',
                "error_details": data["error"],
                "filter": {},
                "items": [],
                "total": 0
            }, indent=4))
            errorHandler(data["error"], 'Invalid search filter (`Keyword,"fnmatch syntax"`)')

        elif block == 'start':
            print('{{ "filter": {{"key": "{}", "value": "{}"}}, "items": ['.format(data["search_key"], data["search_value"]) )

        elif block == 'item':
            # comma to last block
            if data["count"] > 0:
                print(',')
            json_item = {
                "filename": data["json_path"],
                "content": data["json_content"]
            }
            print(json.dumps(json_item, indent=4))

        elif block == 'end':
            print('\n], "found":', data["count"], '}')
            errorHandler(None, '', 0)

    # text output
    #elif type == 'text':
    else:
        if block == 'error':
            errorHandler(data["error"], 'Invalid search filter (`Keyword,"fnmatch syntax"`)')

        elif block == 'start':
            print('Searching for {} = {}'.format(data["search_key"], data["search_value"]))

        elif block == 'item':
            print('\n' + data["json_path"])
            print(json.dumps(data["json_content"], indent=4))

        elif block == 'end':
            print('\nFound', data["count"])
            errorHandler(None, '', 0)
            
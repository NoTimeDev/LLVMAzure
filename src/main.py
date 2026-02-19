import sys
from pathlib import Path
from lexer import *
from parser import *
from semantic_analysis import *
from compiler import *
import json

argc = len(sys.argv)
argv = sys.argv

if argc < 2:
    print("Must provide a file!")
    exit(1)

input_file = Path(argv[1])

if not input_file.exists():
    print("Path does not exist!")
    exit(1)

with open(input_file) as f:
    tokens = LEXER(f.read(), input_file.name).tokens
    ast = PARSER(tokens, input_file.name).ast
    SEMANTIC_ANALYSIS(ast, input_file.name)
    module = COMPILER(ast, input_file.name)

print(module.module)

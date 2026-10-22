#!/bin/bash
cd /app
python -m pytest /tests/test_outputs.py -rA -p no:cacheprovider
if [ $? -eq 0 ]; then echo 1 > /logs/verifier/reward.txt; else echo 0 > /logs/verifier/reward.txt; fi

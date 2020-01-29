#! /bin/bash
while read line
do
    echo "Processing $line"
    python3 scraper.py -S $line -r buster -a amd64 -C -t inputs --bootstrap-servers localhost:9092
done < "${1:-/dev/stdin}"
